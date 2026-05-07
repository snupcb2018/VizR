
# VizR: RNASeq Visualization Tool (Flask + React)

## 1. Overview

VizR is a user-friendly web application designed to help researchers automatically analyze and visualize RNASeq data. It provides a clean, intuitive interface to manage analysis pipelines (called "Workbenches"), track their status, and explore results through various charts and tables.

This application is built with a **Flask** backend serving a modern **React** frontend. This document serves as a technical guide for developers working on the full stack.

**Core Technologies:**

*   **Backend:** Python 3, Flask
*   **Frontend Framework:** React 19
*   **Frontend Language:** TypeScript
*   **Styling:** Tailwind CSS (via CDN)
*   **Charting:** Recharts
*   **Module System:** ES Modules with an `importmap` in `index.html` (no build step for the frontend)

---

## 2. Project Architecture

The project is structured as a monolithic Flask application that serves the frontend and provides a JSON API.

*   **Flask Backend:** Responsible for serving the main `index.html` file, static assets, and providing API endpoints for data operations (e.g., fetching workbench information).
*   **React Frontend:** A single-page application (SPA) running in the user's browser. It handles all UI rendering, user interactions, and communicates with the Flask backend via API calls.

### Suggested File Structure

To integrate the frontend with Flask, the project files should be organized as follows:

```
/
├── app.py                      # Main Flask application file
├── requirements.txt            # Python dependencies
├── static/                     # For all JS/TSX files, components, and pages
│   ├── components/
│   ├── pages/
│   ├── App.tsx
│   ├── constants.tsx
│   ├── index.tsx
│   └── types.ts
└── templates/
    └── index.html              # Main HTML entry point (served by Flask)
```

---

## 3. Frontend Details

The frontend is a self-contained React application.

### 3.1. Frontend Source Structure

*   **`index.html`**: The main HTML file, which should be placed in the Flask `templates/` directory. It includes CDN links for React, Tailwind, and Recharts, and uses an `importmap` to manage modules without a build step.
*   **`index.tsx`**: The entry point for the React application, located in `static/`.
*   **`App.tsx`**: The root component, responsible for client-side routing and top-level state management.
*   **`components/`**: Contains reusable UI components like `Sidebar`, `Header`, `Modal`, and `StatusBadge`.
*   **`pages/`**: Contains top-level components for each view, such as `Dashboard`, `WorkbenchOverview`, and `WorkbenchDetail`.
*   **`types.ts`**: Defines TypeScript types for data structures like `Workbench`.
*   **`constants.tsx`**: Contains mock data. In a production environment, this data would be fetched from the Flask API.

### 3.2. Key Frontend Features

*   **Client-Side Routing:** `App.tsx` uses `useState` to manage the `currentPage`, simulating navigation between different pages without full page reloads.
*   **Component-Based UI:** The UI is broken down into logical, reusable components for maintainability.
*   **Data Visualization:** The `recharts` library is used to create interactive charts for the Dashboard (`PieChart`) and Workbench Detail (`BarChart`) pages.
*   **Styling:** The UI is styled with Tailwind CSS utility classes. A custom `breathe` animation is defined in `index.html` to provide a dynamic visual effect for the "Running" status badge.

---

## 4. Backend (Flask) Integration

### 4.1. Serving the Application

The Flask backend's primary role is to serve the `index.html` file, which bootstraps the React application. You will need to adjust the script paths in `index.html` to point to the `static` directory (e.g., `<script type="module" src="{{ url_for('static', filename='index.tsx') }}"></script>`).

**Example `app.py`:**

```python
from flask import Flask, render_template, url_for

app = Flask(__name__, template_folder='templates', static_folder='static')

# This route will catch all paths and serve the main index.html
# The React app will then handle the specific path on the client side.
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    """Serves the main index.html file for the React application."""
    return render_template("index.html")

if __name__ == '__main__':
    app.run(debug=True)
```

### 4.2. API Endpoints

The backend will expose API endpoints that the React frontend can call to fetch and manipulate data. This replaces the need for `constants.tsx` on the frontend.

**Example API Endpoint in `app.py`:**

```python
from flask import jsonify

# This mock data would come from a database in a real application
MOCK_WORKBENCHES = [
  {
    "id": 1,
    "name": "Arabidopsis thaliana Cold Stress Study",
    "status": "Running",
    "createdAt": "2024-07-20",
    "lastUpdated": "2 minutes ago",
  },
  # ... other workbenches from constants.tsx
]

@app.route('/api/workbenches', methods=['GET'])
def get_workbenches():
    """Returns a list of all workbenches."""
    return jsonify(MOCK_WORKBENCHES)
```

The React app would then fetch this data instead of importing it locally:

```javascript
// Example fetch call in a React component
fetch('/api/workbenches')
  .then(response => response.json())
  .then(data => {
    // Set the workbench data in the component's state
    console.log(data);
  });
```

---

## 5. Getting Started

To run the full-stack application:

1.  **Set up the file structure:**
    *   Organize your files as described in section 2.
    *   Create `app.py` and `requirements.txt` in the root directory.

2.  **Set up the Python Environment:**
    ```bash
    # Create a virtual environment
    python3 -m venv venv

    # Activate it
    # On Windows: venv\Scripts\activate
    # On macOS/Linux: source venv/bin/activate
    ```

3.  **Install Dependencies:**
    Create a `requirements.txt` file with the content `Flask`, then install it:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the Flask Server:**
    ```bash
    flask run
    ```

5.  **Access the Application:**
    Open your web browser and navigate to `http://127.0.0.1:5000`.

---

## 6. Future Development

*   **Database Integration**: Connect the Flask backend to a database (e.g., PostgreSQL, SQLite) using an ORM like SQLAlchemy to persist data.
*   **Authentication**: Implement user authentication and authorization using a Flask extension like Flask-Login or Flask-JWT-Extended.
*   **Frontend Build Process**: For production, introduce a build tool like Vite to bundle and optimize the frontend assets, which would then be served from the Flask `static` folder.
*   **API Expansion**: Build out a full RESTful API for creating, updating, and deleting workbenches and other resources.
*   **Implement Core Logic**: Develop the backend logic for running the actual RNASeq analysis pipelines, potentially using Celery for asynchronous tasks.
