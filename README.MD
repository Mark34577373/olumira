# Olumira

**A caregiver-support platform designed to help organize routines, communication, observations, and helpful resources in one place.**

## Why I Built Olumira

Olumira began with a simple observation: supporting someone with substantial support needs often involves keeping track of routines, communication, activities, and small changes throughout the day.

I wanted to explore how software could make that process more organized and easier to manage.

Rather than building another general-purpose productivity app, I designed Olumira around four core questions:

* **Routines** — What needs to happen?
* **Communication** — What does the person want or need?
* **Observations** — What happened?
* **Resources** — What can a caregiver learn or try?

## Features

### Dashboard

A central view showing:

* Today's routine progress
* Morning routine tasks
* Quick actions
* Recent observations

### Routines

Caregivers can:

* View routine tasks
* Mark tasks as complete
* Track progress
* See progress reflected on the dashboard

### Communication

A visual communication interface with selectable options for common needs and activities, including:

* Thirsty
* Hungry
* Bathroom
* Tired
* Play
* Outside
* School
* Music
* Quiet time

The interface displays the selected communication choice in a simple, easy-to-understand format.

### Observations

Caregivers can record information about activities and events, including:

* Activity
* Date
* Notes
* Mood
* Tags

Saved observations are stored in the application's SQLite database and can be displayed within the dashboard.

### Resources

A caregiver reference library organized around topics such as:

* Communication
* Daily activities
* Routines
* Learning
* Safety
* Caregiver support

## How It Works

Olumira uses a Flask backend connected to a SQLite database.

The general flow is:

```text
User
 ↓
HTML / CSS / JavaScript Interface
 ↓
Flask Application
 ↓
Service Layer
 ↓
SQLite Database
```

For example, when a caregiver completes a routine:

```text
Click Routine
 ↓
Flask receives request
 ↓
Routine status updated
 ↓
SQLite stores completion
 ↓
Dashboard recalculates progress
```

## Tech Stack

* **Python**
* **Flask**
* **SQLite**
* **HTML**
* **CSS**
* **JavaScript**
* **Jinja2**
* **Git / GitHub**

## Project Structure

```text
olumira/
├── app.py
├── README.md
├── requirements.txt
├── services/
│   ├── database.py
│   ├── routines.py
│   └── observations.py
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── routines.html
│   ├── communication.html
│   ├── observations.html
│   └── resources.html
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
└── database/
    └── olumira.db

## Current Status

Olumira is currently a functional MVP.

The application includes:

* Working Flask backend
* SQLite data storage
* Functional routines
* Dynamic routine progress
* Visual communication interface
* Saved observations
* Caregiver resources
* Responsive interface

## Future Improvements

Potential future development includes:

* User accounts and caregiver profiles
* Multiple routines and schedules
* Custom communication cards
* More advanced observation analytics
* Data visualization
* Exportable caregiver reports
* Accessibility improvements
* Cloud database support
* Secure deployment
* Mobile application support

## Project Goal

Olumira is an exploration of how software can turn everyday caregiver information into a more organized and accessible experience.

The project combines **software development, accessibility, and human-centered design** to address a problem I have encountered personally.
