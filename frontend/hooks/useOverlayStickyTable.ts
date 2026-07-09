import { useEffect, useRef, useState } from 'react';

export interface StickyTableOverlayState {
  visible: boolean;
  top: number;
  left: number;
  width: number;
  tableWidth: number;
  scrollLeft: number;
  height: number;
}

interface UseOverlayStickyTableOptions {
  enabled: boolean;
  dependencyKey: string;
  visibilityThreshold?: number;
}

const EMPTY_OVERLAY: StickyTableOverlayState = {
  visible: false,
  top: 0,
  left: 0,
  width: 0,
  tableWidth: 0,
  scrollLeft: 0,
  height: 0,
};

export function useOverlayStickyTable({
  enabled,
  dependencyKey,
  visibilityThreshold = 320,
}: UseOverlayStickyTableOptions) {
  const [showScrollToTopButton, setShowScrollToTopButton] = useState(false);
  const [overlayHeader, setOverlayHeader] = useState<StickyTableOverlayState>(EMPTY_OVERLAY);
  const [topScrollbarWidth, setTopScrollbarWidth] = useState(0);

  const scrollTargetRef = useRef<HTMLElement | Window | null>(null);
  const tableSectionRef = useRef<HTMLDivElement | null>(null);
  const topScrollbarRef = useRef<HTMLDivElement | null>(null);
  const floatingTopScrollbarRef = useRef<HTMLDivElement | null>(null);
  const tableWrapperRef = useRef<HTMLDivElement | null>(null);
  const tableRef = useRef<HTMLTableElement | null>(null);
  const tableTheadRef = useRef<HTMLTableSectionElement | null>(null);

  useEffect(() => {
    if (!enabled) {
      setShowScrollToTopButton(false);
      scrollTargetRef.current = null;
      return;
    }

    const section = tableSectionRef.current;
    if (!section) {
      return;
    }

    const findScrollParent = (node: HTMLElement | null): HTMLElement | null => {
      let current = node?.parentElement ?? null;
      while (current) {
        const styles = window.getComputedStyle(current);
        const overflowY = styles.overflowY;
        const isScrollable =
          (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') &&
          current.scrollHeight > current.clientHeight + 4;
        if (isScrollable) {
          return current;
        }
        current = current.parentElement;
      }
      return null;
    };

    const scrollTarget = findScrollParent(section) ?? window;
    scrollTargetRef.current = scrollTarget;
    const updateVisibility = () => {
      const scrollTop =
        scrollTarget === window
          ? window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0
          : scrollTarget.scrollTop;
      setShowScrollToTopButton(scrollTop > visibilityThreshold);
    };

    updateVisibility();
    scrollTarget.addEventListener('scroll', updateVisibility, { passive: true });
    return () => {
      scrollTarget.removeEventListener('scroll', updateVisibility);
      if (scrollTargetRef.current === scrollTarget) {
        scrollTargetRef.current = null;
      }
    };
  }, [enabled, dependencyKey, visibilityThreshold]);

  useEffect(() => {
    if (!enabled) {
      setTopScrollbarWidth(0);
      return;
    }

    const topScrollbar = topScrollbarRef.current;
    const floatingScrollbar = floatingTopScrollbarRef.current;
    const tableWrapper = tableWrapperRef.current;
    const table = tableRef.current;

    if (!topScrollbar || !tableWrapper || !table) {
      setTopScrollbarWidth(0);
      return;
    }

    let syncingFromTop = false;
    let syncingFromFloating = false;
    let syncingFromTable = false;

    const syncMetrics = () => {
      setTopScrollbarWidth(table.scrollWidth);
    };

    const handleTopScroll = () => {
      if (syncingFromTable || syncingFromFloating) return;
      syncingFromTop = true;
      tableWrapper.scrollLeft = topScrollbar.scrollLeft;
      if (floatingScrollbar) {
        floatingScrollbar.scrollLeft = topScrollbar.scrollLeft;
      }
      requestAnimationFrame(() => {
        syncingFromTop = false;
      });
    };

    const handleFloatingScroll = () => {
      if (!floatingScrollbar || syncingFromTable || syncingFromTop) return;
      syncingFromFloating = true;
      tableWrapper.scrollLeft = floatingScrollbar.scrollLeft;
      topScrollbar.scrollLeft = floatingScrollbar.scrollLeft;
      requestAnimationFrame(() => {
        syncingFromFloating = false;
      });
    };

    const handleTableScroll = () => {
      if (syncingFromTop || syncingFromFloating) return;
      syncingFromTable = true;
      topScrollbar.scrollLeft = tableWrapper.scrollLeft;
      if (floatingScrollbar) {
        floatingScrollbar.scrollLeft = tableWrapper.scrollLeft;
      }
      requestAnimationFrame(() => {
        syncingFromTable = false;
      });
    };

    syncMetrics();
    topScrollbar.scrollLeft = tableWrapper.scrollLeft;
    if (floatingScrollbar) {
      floatingScrollbar.scrollLeft = tableWrapper.scrollLeft;
    }

    topScrollbar.addEventListener('scroll', handleTopScroll, { passive: true });
    floatingScrollbar?.addEventListener('scroll', handleFloatingScroll, { passive: true });
    tableWrapper.addEventListener('scroll', handleTableScroll, { passive: true });
    window.addEventListener('resize', syncMetrics);

    return () => {
      topScrollbar.removeEventListener('scroll', handleTopScroll);
      floatingScrollbar?.removeEventListener('scroll', handleFloatingScroll);
      tableWrapper.removeEventListener('scroll', handleTableScroll);
      window.removeEventListener('resize', syncMetrics);
    };
  }, [enabled, dependencyKey, overlayHeader.visible]);

  useEffect(() => {
    if (!enabled) {
      setOverlayHeader(EMPTY_OVERLAY);
      return;
    }

    const section = tableSectionRef.current;
    const table = tableRef.current;
    const thead = tableTheadRef.current;

    if (!section || !table || !thead) {
      setOverlayHeader(current => (current.visible ? EMPTY_OVERLAY : current));
      return;
    }

    const findScrollParent = (node: HTMLElement | null): HTMLElement | Window => {
      let current = node?.parentElement ?? null;
      while (current) {
        const styles = window.getComputedStyle(current);
        const overflowY = styles.overflowY;
        const isScrollable =
          (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') &&
          current.scrollHeight > current.clientHeight + 4;
        if (isScrollable) {
          return current;
        }
        current = current.parentElement;
      }
      return window;
    };

    const scrollParent = findScrollParent(section);
    const horizontalScrollTarget = tableWrapperRef.current;
    const updateOverlay = () => {
      const tableRect = table.getBoundingClientRect();
      const wrapperRect = (horizontalScrollTarget ?? table).getBoundingClientRect();
      const theadRect = thead.getBoundingClientRect();
      const headerHeight = theadRect.height || 40;
      const containerTop = scrollParent === window ? 0 : (scrollParent as HTMLElement).getBoundingClientRect().top;
      const shouldShow =
        tableRect.top <= containerTop &&
        tableRect.bottom > containerTop + headerHeight + 8;

      setOverlayHeader({
        visible: shouldShow,
        top: containerTop,
        left: wrapperRect.left,
        width: wrapperRect.width,
        tableWidth: tableRect.width,
        scrollLeft: horizontalScrollTarget?.scrollLeft ?? 0,
        height: headerHeight,
      });
    };

    updateOverlay();
    const handleScrollOrResize = () => updateOverlay();

    if (scrollParent === window) {
      window.addEventListener('scroll', handleScrollOrResize, { passive: true });
    } else {
      scrollParent.addEventListener('scroll', handleScrollOrResize, { passive: true });
    }
    horizontalScrollTarget?.addEventListener('scroll', handleScrollOrResize, { passive: true });
    window.addEventListener('resize', handleScrollOrResize);

    return () => {
      if (scrollParent === window) {
        window.removeEventListener('scroll', handleScrollOrResize);
      } else {
        scrollParent.removeEventListener('scroll', handleScrollOrResize);
      }
      horizontalScrollTarget?.removeEventListener('scroll', handleScrollOrResize);
      window.removeEventListener('resize', handleScrollOrResize);
    };
  }, [enabled, dependencyKey]);

  const handleScrollToTop = () => {
    const target = scrollTargetRef.current;
    if (target && target !== window) {
      target.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return {
    showScrollToTopButton,
    overlayHeader,
    topScrollbarWidth,
    handleScrollToTop,
    refs: {
      scrollTargetRef,
      tableSectionRef,
      topScrollbarRef,
      floatingTopScrollbarRef,
      tableWrapperRef,
      tableRef,
      tableTheadRef,
    },
  };
}
