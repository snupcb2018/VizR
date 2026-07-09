"""
Resource monitoring utilities for VizR pipeline.

This module provides CPU usage monitoring with 5-line compressed braille visualization.
Automatically monitors CPU usage over 1-minute intervals with 10-second sampling.
"""

import os
import time
import threading
import logging
import psutil
from datetime import datetime
from typing import List, Dict, Any, Optional


class FiveLineBrailleVisualizer:
    """
    5-line compressed braille CPU usage visualizer.
    
    Converts CPU usage data into a compact braille chart that shows:
    - 6 samples (60 seconds, 10-second intervals) compressed into 3 braille characters
    - 5 vertical levels representing 0-20%, 20-40%, 40-60%, 60-80%, 80-100%
    - Continuous visualization without gaps between time periods
    """
    
    def __init__(self):
        self.height_labels = ["100%", " 80%", " 60%", " 40%", " 20%"]
    
    def create_5line_timeline_chart(self, samples: List[Dict[str, Any]]) -> List[str]:
        """
        Create 5-line timeline braille chart from CPU samples.
        Each sample gets its own braille character showing CPU level.
        
        Args:
            samples: List of CPU sample dictionaries with 'cpu_percent' and 'timestamp'
            
        Returns:
            List of 5 strings representing each line of the chart
        """
        # Generate 5 lines - each sample gets one braille character per line
        lines = ['', '', '', '', '']
        
        for sample in samples:
            cpu_percent = sample['cpu_percent']
            
            # For each line, create appropriate braille character
            for line_idx in range(5):
                braille_char = self._get_timeline_braille(cpu_percent, line_idx)
                lines[line_idx] += braille_char
        
        return lines
    
    def _get_timeline_braille(self, cpu_percent: float, line_idx: int) -> str:
        """
        Get single braille character for vertical bar chart at specific line.
        Each line represents a 20% band, filled from bottom up like a bar chart.
        
        Args:
            cpu_percent: CPU percentage (0-100)
            line_idx: Line index (0=top/80-100%, 4=bottom/0-20%)
            
        Returns:
            Single braille character
        """
        # Each line covers 20% range: line 0=80-100%, line 1=60-80%, etc.
        line_min = (4 - line_idx) * 20  # 80, 60, 40, 20, 0
        line_max = line_min + 20        # 100, 80, 60, 40, 20
        
        # Vertical bar chart logic:
        # If CPU is above this line's max, fill completely
        # If CPU is within this line's range, show relative position
        # If CPU is below this line's min, show empty
        
        if cpu_percent >= line_max:
            # CPU is above this line - fill completely
            return '⣿'
        elif cpu_percent >= line_min:
            # CPU is within this line's range - show relative position
            relative_cpu = cpu_percent - line_min  # 0-20 range
            braille_level = min(int((relative_cpu / 20) * 8), 7)
            
            # Use progressive braille patterns for smooth bar effect
            braille_patterns = [
                '⠀',  # 0: empty
                '⡀',  # 1: bottom dot (⠈ -> ⡀)
                '⡄',  # 2: bottom + lower middle 
                '⡆',  # 3: bottom + middle
                '⡇',  # 4: bottom + middle + upper middle
                '⡿',  # 5: almost full (missing top)
                '⣿',  # 6: full
                '⣿'   # 7: full
            ]
            
            return braille_patterns[braille_level]
        else:
            # CPU is below this line's range - show empty
            return '⠀'
    
    def _create_dual_braille(self, left_cpu: float, right_cpu: float) -> str:
        """
        Create a single braille character representing two CPU values.
        
        Args:
            left_cpu: CPU percentage for left half of time period
            right_cpu: CPU percentage for right half of time period
            
        Returns:
            Single braille Unicode character
        """
        # Convert CPU to 5 levels (0-4)
        left_level = min(int(left_cpu / 20), 4)
        right_level = min(int(right_cpu / 20), 4)
        
        # Braille dot positions:
        # 1 4
        # 2 5
        # 3 6
        # 7 8
        
        left_dots = self._get_left_dots(left_level)
        right_dots = self._get_right_dots(right_level)
        
        # Combine dot patterns and create Unicode braille character
        combined_value = left_dots | right_dots
        return chr(0x2800 + combined_value)
    
    def _get_left_dots(self, level: int) -> int:
        """Get braille dots pattern for left CPU value (uses dots 1,2,3,7)"""
        patterns = {
            0: 0b00000000,  # Empty
            1: 0b01000000,  # Dot 7 (bottom)
            2: 0b01000100,  # Dots 3,7 (middle-bottom)
            3: 0b01000110,  # Dots 2,3,7 (middle)
            4: 0b01000111   # Dots 1,2,3,7 (top)
        }
        return patterns.get(level, 0)
    
    def _get_right_dots(self, level: int) -> int:
        """Get braille dots pattern for right CPU value (uses dots 4,5,6,8)"""
        patterns = {
            0: 0b00000000,  # Empty
            1: 0b10000000,  # Dot 8 (bottom)
            2: 0b10100000,  # Dots 6,8 (middle-bottom)
            3: 0b10110000,  # Dots 5,6,8 (middle)
            4: 0b10111000   # Dots 4,5,6,8 (top)
        }
        return patterns.get(level, 0)
    
    def _get_line_character(self, left_cpu: float, right_cpu: float, line_idx: int) -> str:
        """
        Get the braille character for a specific line based on CPU levels.
        Uses proper braille dots to show fine-grained CPU usage within each 20% band.
        
        Args:
            left_cpu: Left CPU percentage  
            right_cpu: Right CPU percentage
            line_idx: Line index (0=top, 4=bottom)
            
        Returns:
            Single braille character representing both CPU values for this line
        """
        # Each line covers 20% range: line 0=80-100%, line 1=60-80%, etc.
        line_min = (4 - line_idx) * 20  # 80, 60, 40, 20, 0
        line_max = line_min + 20        # 100, 80, 60, 40, 20
        
        # Check if CPU values fall within this line's range
        left_in_range = line_min <= left_cpu < line_max or (line_idx == 0 and left_cpu >= 80)
        right_in_range = line_min <= right_cpu < line_max or (line_idx == 0 and right_cpu >= 80)
        
        # If neither value is in this line's range, return empty braille
        if not left_in_range and not right_in_range:
            return '⠀'  # Empty braille
        
        # Calculate fine-grained levels within the 20% range (0-7 for 8 braille levels)
        def get_braille_level(cpu_val, in_range):
            if not in_range:
                return 0
            # Map CPU within the 20% band to 0-7 braille levels  
            relative_cpu = cpu_val - line_min  # 0-20 range
            return min(int((relative_cpu / 20) * 8), 7)
        
        left_level = get_braille_level(left_cpu, left_in_range) 
        right_level = get_braille_level(right_cpu, right_in_range)
        
        # Generate braille character using the levels
        return self._create_braille_from_levels(left_level, right_level)
    
    def _create_braille_from_levels(self, left_level: int, right_level: int) -> str:
        """
        Create braille character from two 0-7 levels.
        
        Braille dot positions:
        1 4
        2 5  
        3 6
        7 8
        
        Left side uses dots 1,2,3,7 (4 dots = 8 levels with bottom-up filling)
        Right side uses dots 4,5,6,8 (4 dots = 8 levels with bottom-up filling)
        """
        # Left side dot patterns (bottom-up filling)
        left_patterns = [
            0b00000000,  # 0: ⠀ (empty)
            0b01000000,  # 1: ⡀ (dot 7 only)
            0b01000100,  # 2: ⡄ (dots 3,7)
            0b01000110,  # 3: ⡆ (dots 2,3,7)
            0b01000111,  # 4: ⡇ (dots 1,2,3,7)
            0b01001111,  # 5: dots 1,2,3,4,7 - but 4 is right side, so keep as 1,2,3,7
            0b01000111,  # 6: same as 4 (can't add more left dots)
            0b01000111   # 7: same as 4 (max left dots)
        ]
        
        # Right side dot patterns (bottom-up filling) 
        right_patterns = [
            0b00000000,  # 0: ⠀ (empty)
            0b10000000,  # 1: ⢀ (dot 8 only)
            0b10100000,  # 2: ⢠ (dots 6,8)
            0b10110000,  # 3: ⢰ (dots 5,6,8)
            0b10111000,  # 4: ⢸ (dots 4,5,6,8)
            0b10111000,  # 5: same as 4 (max right dots)
            0b10111000,  # 6: same as 4 
            0b10111000   # 7: same as 4 
        ]
        
        # Combine left and right patterns
        combined = left_patterns[left_level] | right_patterns[right_level]
        return chr(0x2800 + combined)
    
    def format_chart(self, lines: List[str], samples: List[Dict[str, Any]], 
                    process_name: str = "CPU") -> str:
        """
        Format the 5-line chart with labels and statistics.
        
        Args:
            lines: List of chart lines
            samples: Original CPU samples
            process_name: Name for the process being monitored
            
        Returns:
            Formatted multi-line string ready for logging
        """
        cpu_values = [s['cpu_percent'] for s in samples]
        avg_cpu = sum(cpu_values) / len(cpu_values) if cpu_values else 0
        max_cpu = max(cpu_values) if cpu_values else 0
        min_cpu = min(cpu_values) if cpu_values else 0
        
        # Status emoji based on average CPU
        status = self._get_status_emoji(avg_cpu)
        
        chart_output = f"{status} [{process_name}-{os.getpid()}] 1분간 사용률 (브라일 타임라인):\n"
        
        # 5-line chart with percentage labels
        for i, line in enumerate(lines):
            chart_output += f"   {self.height_labels[i]} {line}\n"
        
        # Time axis - show start, middle, and end times
        sample_count = len(samples)
        if sample_count > 0:
            # Create time axis based on actual sample count
            time_axis = "        "
            time_axis += "0s"
            
            # Add padding to center position
            middle_pos = sample_count // 2
            padding_middle = " " * (middle_pos - 2)  # Adjust for "0s" length
            time_axis += padding_middle
            
            # Add middle time
            middle_time = f"{sample_count * 3 // 2}s"
            time_axis += middle_time
            
            # Add padding to end position  
            end_pos = sample_count - len(f"{sample_count * 3}s")
            padding_end = " " * (end_pos - len(middle_time))
            time_axis += padding_end
            
            # Add end time
            time_axis += f"{sample_count * 3}s"
            
            chart_output += time_axis + "\n"
        else:
            chart_output += f"        0s                                                     60s\n"
            
        chart_output += f"        평균:{avg_cpu:.1f}% 최대:{max_cpu:.1f}% 최소:{min_cpu:.1f}%"
        
        return chart_output
    
    def _get_status_emoji(self, avg_cpu: float) -> str:
        """Get status emoji based on average CPU usage"""
        if avg_cpu < 20:
            return "😴"  # Idle
        elif avg_cpu < 50:
            return "🟢"  # Normal
        elif avg_cpu < 80:
            return "🟡"  # Warning
        else:
            return "🔥"  # High load


class CPUMonitor:
    """
    Automatic CPU usage monitor with 5-line braille visualization.
    
    Usage:
        monitor = CPUMonitor()
        monitor.start(logger=my_logger, interval=60, process_name="PIPELINE")
        # ... do work ...
        monitor.stop()
    """
    
    def __init__(self):
        self.visualizer = FiveLineBrailleVisualizer()
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.logger: Optional[logging.Logger] = None
        self.interval = 60  # Default 1 minute
        self.process_name = "CPU"
        self._shutdown_event = threading.Event()
    
    def start(self, logger: Optional[logging.Logger] = None, 
              interval: int = 60, process_name: str = "CPU") -> None:
        """
        Start CPU monitoring in background thread.
        
        Args:
            logger: Logger instance to use (creates default if None)
            interval: Monitoring interval in seconds (default: 60)
            process_name: Name for the monitoring process (default: "CPU")
        """
        if self.monitoring:
            if self.logger:
                self.logger.warning(f"⚠️  [CPU-{os.getpid()}] Monitor already running")
            return
        
        # Setup logger
        if logger is None:
            from backend.utils.logger import setup_module_logger
            self.logger = setup_module_logger(__name__, 'INFO')
        else:
            self.logger = logger
        
        self.interval = interval
        self.process_name = process_name
        self.monitoring = True
        self._shutdown_event.clear()
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name=f"CPUMonitor-{process_name}-{os.getpid()}",
            daemon=True
        )
        self.monitor_thread.start()
        
        self.logger.info(
            f"🚀 [CPU-{os.getpid()}] Monitor started: {process_name} "
            f"(interval: {interval}s, PID: {os.getpid()})"
        )
    
    def stop(self) -> None:
        """Stop CPU monitoring."""
        if not self.monitoring:
            if self.logger:
                self.logger.warning(f"⚠️  [CPU-{os.getpid()}] Monitor not running")
            return
        
        self.monitoring = False
        self._shutdown_event.set()
        
        # Wait for thread to finish (max 5 seconds)
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5.0)
        
        if self.logger:
            self.logger.info(f"🛑 [CPU-{os.getpid()}] Monitor stopped: {self.process_name}")
    
    def collect_and_log(self) -> None:
        """
        Collect CPU usage for 1 minute and log 5-line braille chart.
        Now collects more frequent samples for better time resolution.
        """
        if not self.logger:
            return
        
        samples = []
        
        try:
            # Collect 20 samples over 60 seconds (3-second intervals for better resolution)
            sample_interval = 3  # 3 seconds
            sample_count = 20   # 60 seconds / 3 seconds = 20 samples
            
            for i in range(sample_count):
                if not self.monitoring:  # Check if we should stop
                    break
                
                start_time = time.time()
                cpu_percent = psutil.cpu_percent(interval=sample_interval)
                
                samples.append({
                    'timestamp': datetime.now(),
                    'cpu_percent': cpu_percent,
                    'time_offset': i * sample_interval  # 0, 3, 6, 9, ... 57
                })
                
                # Log progress for first collection
                if len(samples) == 1:
                    self.logger.debug(
                        f"📊 [CPU-{os.getpid()}] Starting collection... "
                        f"({i+1}/{sample_count}: {cpu_percent:.1f}%)"
                    )
            
            if samples:
                # Generate and log 5-line braille timeline chart
                lines = self.visualizer.create_5line_timeline_chart(samples)
                formatted_chart = self.visualizer.format_chart(
                    lines, samples, self.process_name
                )
                
                self.logger.info(formatted_chart)
                
                # Debug information
                self.logger.debug(
                    f"🔍 [CPU-{os.getpid()}] Raw samples: " +
                    ", ".join([f"{s['cpu_percent']:.1f}%" for s in samples])
                )
                
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"💥 [CPU-{os.getpid()}] Error during monitoring: {e}"
                )
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop running in background thread."""
        self.logger.info(
            f"🔄 [CPU-{os.getpid()}] Monitoring loop started for {self.process_name}"
        )
        
        while self.monitoring:
            try:
                self.collect_and_log()
                
                # Wait for next interval or until shutdown
                if self._shutdown_event.wait(timeout=self.interval):
                    break  # Shutdown requested
                    
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"💥 [CPU-{os.getpid()}] Monitor loop error: {e}"
                    )
                
                # Wait a bit before retrying to avoid spam
                if self._shutdown_event.wait(timeout=10):
                    break
        
        self.logger.info(
            f"🏁 [CPU-{os.getpid()}] Monitoring loop finished for {self.process_name}"
        )
    
    def is_running(self) -> bool:
        """Check if monitoring is currently active."""
        return self.monitoring and (
            self.monitor_thread is not None and 
            self.monitor_thread.is_alive()
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Get current monitoring status information."""
        return {
            'monitoring': self.monitoring,
            'thread_alive': self.monitor_thread.is_alive() if self.monitor_thread else False,
            'process_name': self.process_name,
            'interval': self.interval,
            'pid': os.getpid(),
            'thread_name': self.monitor_thread.name if self.monitor_thread else None
        }


# Convenience function for quick monitoring
def start_cpu_monitoring(logger: Optional[logging.Logger] = None, 
                        interval: int = 60, 
                        process_name: str = "CPU") -> CPUMonitor:
    """
    Quick start CPU monitoring.
    
    Args:
        logger: Logger to use
        interval: Monitoring interval in seconds
        process_name: Name for the monitoring process
        
    Returns:
        CPUMonitor instance (call .stop() when done)
    
    Example:
        monitor = start_cpu_monitoring(my_logger, 60, "PIPELINE")
        # ... do work ...
        monitor.stop()
    """
    monitor = CPUMonitor()
    monitor.start(logger=logger, interval=interval, process_name=process_name)
    return monitor


# Context manager for automatic cleanup
class CPUMonitorContext:
    """
    Context manager for automatic CPU monitoring with cleanup.
    
    Usage:
        with CPUMonitorContext(logger=my_logger, process_name="PIPELINE"):
            # ... do work ...
            # monitoring automatically stops when exiting context
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None, 
                 interval: int = 60, process_name: str = "CPU"):
        self.monitor = CPUMonitor()
        self.logger = logger
        self.interval = interval
        self.process_name = process_name
    
    def __enter__(self) -> CPUMonitor:
        self.monitor.start(
            logger=self.logger, 
            interval=self.interval, 
            process_name=self.process_name
        )
        return self.monitor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.monitor.stop()


if __name__ == "__main__":
    # Test/demo code
    import sys
    
    # Setup basic logging with debug level
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    from backend.utils.logger import setup_module_logger
    logger = setup_module_logger("test", 'INFO')
    
    print("🧪 Testing CPU Monitor...")
    print("Starting 5-line braille CPU monitoring for 2 minutes...")
    
    # Test basic usage
    monitor = CPUMonitor()
    monitor.start(logger=logger, interval=60, process_name="TEST")
    
    try:
        # Let it run for 2 monitoring cycles
        time.sleep(999999)
    except KeyboardInterrupt:
        print("\n⏹️  Stopping monitor...")
    finally:
        monitor.stop()
    
    print("✅ Test completed!")