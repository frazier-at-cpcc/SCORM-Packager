"""
SCORM Package Generator
A Streamlit app to create SCORM 1.2 packages that embed external URLs with time tracking.
"""

import streamlit as st
import zipfile
import io
import re
from datetime import datetime

# Page config
st.set_page_config(
    page_title="SCORM Package Generator",
    page_icon="📦",
    layout="centered"
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        max-width: 800px;
        margin: 0 auto;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #e7f3ff;
        border: 1px solid #b6d4fe;
        color: #084298;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

def sanitize_filename(name: str) -> str:
    """Convert course name to safe filename."""
    # Remove special characters, replace spaces with underscores
    safe = re.sub(r'[^\w\s-]', '', name)
    safe = re.sub(r'[\s]+', '_', safe)
    return safe[:50]  # Limit length

def generate_manifest(course_id: str, course_title: str, mastery_score: int) -> str:
    """Generate imsmanifest.xml content."""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{course_id}" version="1.0"
    xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
    xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                        http://www.imsglobal.org/xsd/imsmd_rootv1p2p1 imsmd_rootv1p2p1.xsd
                        http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">

    <metadata>
        <schema>ADL SCORM</schema>
        <schemaversion>1.2</schemaversion>
    </metadata>

    <organizations default="org1">
        <organization identifier="org1">
            <title>{course_title}</title>
            <item identifier="item1" identifierref="resource1">
                <title>{course_title}</title>
                <adlcp:masteryscore>{mastery_score}</adlcp:masteryscore>
            </item>
        </organization>
    </organizations>

    <resources>
        <resource identifier="resource1" type="webcontent" adlcp:scormtype="sco" href="index.html">
            <file href="index.html"/>
            <file href="scormapi.js"/>
        </resource>
    </resources>
</manifest>'''

def generate_scorm_api() -> str:
    """Generate scormapi.js content."""
    return '''/**
 * SCORM 1.2 API Wrapper
 * Handles communication between the course content and the LMS
 */

var SCORM = {
    API: null,
    isInitialized: false,

    findAPI: function(win) {
        var attempts = 0;
        var maxAttempts = 500;

        while ((!win.API) && (win.parent) && (win.parent != win) && (attempts < maxAttempts)) {
            attempts++;
            win = win.parent;
        }

        if (win.API) {
            return win.API;
        }

        if (win.opener && win.opener.API) {
            return win.opener.API;
        }

        if (win.opener) {
            return this.findAPI(win.opener);
        }

        return null;
    },

    init: function() {
        this.API = this.findAPI(window);

        if (this.API) {
            var result = this.API.LMSInitialize("");
            if (result === "true" || result === true) {
                this.isInitialized = true;
                this.setStatus("incomplete");
                console.log("SCORM: Successfully initialized");
                return true;
            }
        }

        console.log("SCORM: Could not initialize - API not found or initialization failed");
        return false;
    },

    setStatus: function(status) {
        if (this.isInitialized && this.API) {
            this.API.LMSSetValue("cmi.core.lesson_status", status);
            this.API.LMSCommit("");
        }
    },

    setScore: function(score) {
        if (this.isInitialized && this.API) {
            this.API.LMSSetValue("cmi.core.score.raw", score);
            this.API.LMSSetValue("cmi.core.score.min", "0");
            this.API.LMSSetValue("cmi.core.score.max", "100");
            this.API.LMSCommit("");
        }
    },

    complete: function() {
        this.setStatus("completed");
        this.setScore(100);
        console.log("SCORM: Course marked as completed");
    },

    pass: function() {
        this.setStatus("passed");
        this.setScore(100);
        console.log("SCORM: Course marked as passed");
    },

    finish: function() {
        if (this.isInitialized && this.API) {
            this.API.LMSCommit("");
            this.API.LMSFinish("");
            this.isInitialized = false;
            console.log("SCORM: Session terminated");
        }
    },

    getValue: function(element) {
        if (this.isInitialized && this.API) {
            return this.API.LMSGetValue(element);
        }
        return "";
    },

    setValue: function(element, value) {
        if (this.isInitialized && this.API) {
            this.API.LMSSetValue(element, value);
            this.API.LMSCommit("");
        }
    }
};

window.onload = function() {
    SCORM.init();
};

window.onunload = function() {
    SCORM.finish();
};

window.onbeforeunload = function() {
    SCORM.finish();
};'''

def generate_html(course_title: str, course_url: str, primary_color: str,
                  expected_duration: int, require_min_time: bool, min_time_minutes: int,
                  subtitle: str = "", additional_info: str = "") -> str:
    """Generate index.html content with time tracking."""

    # Convert hex color to RGB for gradient
    hex_color = primary_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    # Create a darker shade for gradient
    darker = f"#{max(0,r-40):02x}{max(0,g-40):02x}{max(0,b-40):02x}"

    min_time_js = ""
    min_time_check = ""
    if require_min_time:
        min_time_seconds = min_time_minutes * 60
        min_time_js = f"var MIN_TIME_REQUIRED = {min_time_seconds};"
        min_time_check = f'''
            if (totalSeconds < MIN_TIME_REQUIRED) {{
                var remaining = MIN_TIME_REQUIRED - totalSeconds;
                alert('You need to spend at least {min_time_minutes} minutes on this course before marking it complete.\\n\\nTime remaining: ' + formatTime(remaining));
                return;
            }}'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{course_title}</title>
    <script src="scormapi.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html, body {{
            width: 100%;
            height: 100%;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #f5f5f7;
        }}

        .container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 40px 20px;
        }}

        .card {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            padding: 48px;
            max-width: 700px;
            width: 100%;
            text-align: center;
            border-top: 4px solid {primary_color};
        }}

        .logo {{
            width: 60px;
            height: 60px;
            background: {primary_color};
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 24px;
        }}

        .logo svg {{
            width: 32px;
            height: 32px;
            fill: white;
        }}

        h1 {{
            color: #1a1a1a;
            font-size: 26px;
            margin-bottom: 12px;
            font-weight: 600;
            letter-spacing: -0.02em;
        }}

        .subtitle {{
            color: #666666;
            font-size: 15px;
            margin-bottom: 20px;
            line-height: 1.5;
            font-weight: 400;
        }}

        .additional-info {{
            background: #fafafa;
            border: 1px solid #e0e0e0;
            border-left: 3px solid {primary_color};
            padding: 20px;
            border-radius: 4px;
            margin-bottom: 28px;
            text-align: left;
            color: #333333;
            font-size: 13px;
            line-height: 1.7;
        }}

        .additional-info p {{
            margin: 0 0 10px 0;
        }}

        .additional-info p:last-child {{
            margin-bottom: 0;
        }}

        .btn {{
            display: inline-block;
            padding: 12px 28px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            text-decoration: none;
            transition: all 0.2s ease;
            margin: 6px;
            letter-spacing: 0.01em;
        }}

        .btn-primary {{
            background: {primary_color};
            color: white;
        }}

        .btn-primary:hover {{
            background: {darker};
            box-shadow: 0 2px 4px rgba(0,0,0,0.15);
        }}

        .btn-success {{
            background: #00B06B;
            color: white;
        }}

        .btn-success:hover {{
            background: #009959;
        }}

        .btn-success:disabled {{
            background: #cccccc;
            cursor: not-allowed;
        }}

        .btn-secondary {{
            background: #ffffff;
            color: #333333;
            border: 1px solid #d1d1d1;
        }}

        .btn-secondary:hover {{
            background: #f5f5f5;
            border-color: #b3b3b3;
        }}

        .status-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin: 32px 0;
        }}

        .status-box {{
            background: #fafafa;
            border-radius: 4px;
            padding: 20px;
            border: 1px solid #e5e5e5;
            border-left: 3px solid {primary_color};
        }}

        .status-box.time {{
            border-left-color: #FF9500;
        }}

        .status-box.total-time {{
            border-left-color: #00B06B;
        }}

        .status-label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #888888;
            margin-bottom: 8px;
            font-weight: 500;
        }}

        .status-value {{
            font-size: 16px;
            font-weight: 600;
            color: #1a1a1a;
        }}

        .status-value.completed {{
            color: #00B06B;
        }}

        .time-display {{
            font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
            font-size: 20px;
            color: #FF9500;
            font-weight: 500;
        }}

        .total-time-display {{
            font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
            font-size: 20px;
            color: #00B06B;
            font-weight: 500;
        }}

        .instructions {{
            background: #f9f9f9;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            padding: 24px;
            margin-top: 28px;
            text-align: left;
        }}

        .instructions h3 {{
            color: #1a1a1a;
            font-size: 14px;
            margin-bottom: 12px;
            font-weight: 600;
        }}

        .instructions ol {{
            color: #4d4d4d;
            font-size: 13px;
            padding-left: 20px;
            line-height: 1.7;
        }}

        .button-group {{
            margin-top: 25px;
        }}

        .course-opened {{
            display: none;
        }}

        .course-opened.show {{
            display: block;
        }}

        .initial-state.hide {{
            display: none;
        }}

        .timer-notice {{
            background: #f0f4ff;
            border: 1px solid #d0d9f5;
            border-radius: 4px;
            padding: 16px;
            margin-top: 24px;
            font-size: 13px;
            color: #334155;
        }}

        .timer-active {{
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #00B06B;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }}

        .timer-paused {{
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #FF9500;
            border-radius: 50%;
            margin-right: 8px;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}

        .progress-bar-container {{
            background: #e5e5e5;
            border-radius: 2px;
            height: 6px;
            margin-top: 12px;
            overflow: hidden;
        }}

        .progress-bar {{
            background: {primary_color};
            height: 100%;
            border-radius: 2px;
            transition: width 0.5s ease;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2L4 6v6c0 5.55 3.84 10.74 8 12 4.16-1.26 8-6.45 8-12V6l-8-4zm0 2.18l6 3v4.82c0 4.52-2.98 8.69-6 9.88-3.02-1.19-6-5.36-6-9.88V7.18l6-3z"/>
                </svg>
            </div>
            <h1>{course_title}</h1>
            <p class="subtitle">{subtitle if subtitle else 'External Course with Time Tracking'}</p>
            {f'<div class="additional-info">{additional_info}</div>' if additional_info else ''}

            <div class="status-grid">
                <div class="status-box">
                    <div class="status-label">Course Status</div>
                    <div class="status-value" id="statusValue">Not Started</div>
                </div>
                <div class="status-box time">
                    <div class="status-label"><span class="timer-paused" id="timerIndicator"></span>Session Time</div>
                    <div class="time-display" id="sessionTime">00:00:00</div>
                </div>
            </div>

            <div class="status-box total-time" style="margin-bottom: 20px;">
                <div class="status-label">Total Time on Course</div>
                <div class="total-time-display" id="totalTime">00:00:00</div>
                <div class="progress-bar-container">
                    <div class="progress-bar" id="progressBar" style="width: 0%"></div>
                </div>
            </div>

            <div id="initialState" class="initial-state">
                <button class="btn btn-primary" onclick="launchCourse()">
                    Launch Course ↗
                </button>

                <div class="instructions">
                    <h3>Instructions:</h3>
                    <ol>
                        <li>Click "Launch Course" to open the training in a new tab</li>
                        <li>Complete the course in the new tab</li>
                        <li>Keep this window open - it tracks your time</li>
                        <li>Return here and click "Mark Complete" when finished</li>
                    </ol>
                </div>
            </div>

            <div id="courseOpened" class="course-opened">
                <div class="timer-notice">
                    <span class="timer-active" id="activeIndicator"></span>
                    <strong>Timer is running.</strong> Keep this window open while completing the course.
                </div>

                <div class="button-group">
                    <button class="btn btn-primary" onclick="launchCourse()">
                        Reopen Course ↗
                    </button>
                    <button class="btn btn-success" id="completeBtn" onclick="markComplete()">
                        ✓ Mark Complete
                    </button>
                    <button class="btn btn-secondary" onclick="exitCourse()">
                        Exit Course
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script>
        var courseWindow = null;
        var courseURL = "{course_url}";
        var EXPECTED_DURATION = {expected_duration * 60};
        {min_time_js}

        var sessionStartTime = null;
        var sessionSeconds = 0;
        var totalSeconds = 0;
        var timerInterval = null;
        var isTimerRunning = false;

        function formatTime(seconds) {{
            var hrs = Math.floor(seconds / 3600);
            var mins = Math.floor((seconds % 3600) / 60);
            var secs = seconds % 60;
            return String(hrs).padStart(2, '0') + ':' +
                   String(mins).padStart(2, '0') + ':' +
                   String(secs).padStart(2, '0');
        }}

        function formatScormTime(seconds) {{
            var hrs = Math.floor(seconds / 3600);
            var mins = Math.floor((seconds % 3600) / 60);
            var secs = seconds % 60;
            return String(hrs).padStart(4, '0') + ':' +
                   String(mins).padStart(2, '0') + ':' +
                   String(secs).padStart(2, '0') + '.00';
        }}

        function parseScormTime(timeStr) {{
            if (!timeStr || timeStr === '') return 0;
            var parts = timeStr.split(':');
            if (parts.length >= 3) {{
                var hrs = parseInt(parts[0], 10) || 0;
                var mins = parseInt(parts[1], 10) || 0;
                var secs = parseFloat(parts[2]) || 0;
                return hrs * 3600 + mins * 60 + Math.floor(secs);
            }}
            return 0;
        }}

        function updateTimerDisplay() {{
            document.getElementById('sessionTime').textContent = formatTime(sessionSeconds);
            document.getElementById('totalTime').textContent = formatTime(totalSeconds);

            var progress = Math.min((totalSeconds / EXPECTED_DURATION) * 100, 100);
            document.getElementById('progressBar').style.width = progress + '%';
        }}

        function startTimer() {{
            if (isTimerRunning) return;

            isTimerRunning = true;
            sessionStartTime = Date.now();

            var indicator = document.getElementById('timerIndicator');
            indicator.className = 'timer-active';

            timerInterval = setInterval(function() {{
                sessionSeconds++;
                totalSeconds++;
                updateTimerDisplay();

                if (sessionSeconds % 30 === 0) {{
                    commitTimeToScorm();
                }}
            }}, 1000);
        }}

        function pauseTimer() {{
            if (!isTimerRunning) return;

            isTimerRunning = false;
            clearInterval(timerInterval);

            var indicator = document.getElementById('timerIndicator');
            indicator.className = 'timer-paused';

            commitTimeToScorm();
        }}

        function commitTimeToScorm() {{
            if (SCORM.isInitialized) {{
                SCORM.setValue('cmi.core.session_time', formatScormTime(sessionSeconds));
                SCORM.setValue('cmi.suspend_data', JSON.stringify({{
                    totalTime: totalSeconds,
                    lastAccess: new Date().toISOString()
                }}));
            }}
        }}

        function loadTimeFromScorm() {{
            if (SCORM.isInitialized) {{
                var suspendData = SCORM.getValue('cmi.suspend_data');
                if (suspendData && suspendData !== '') {{
                    try {{
                        var data = JSON.parse(suspendData);
                        if (data.totalTime) {{
                            totalSeconds = data.totalTime;
                            updateTimerDisplay();
                        }}
                    }} catch (e) {{
                        console.log('Could not parse suspend_data');
                    }}
                }}

                var totalTimeStr = SCORM.getValue('cmi.core.total_time');
                if (totalTimeStr && totalTimeStr !== '') {{
                    var prevTotal = parseScormTime(totalTimeStr);
                    if (prevTotal > totalSeconds) {{
                        totalSeconds = prevTotal;
                        updateTimerDisplay();
                    }}
                }}
            }}
        }}

        function launchCourse() {{
            courseWindow = window.open(courseURL, '_blank');

            document.getElementById('initialState').classList.add('hide');
            document.getElementById('courseOpened').classList.add('show');

            updateStatus('In Progress');
            SCORM.setStatus('incomplete');
            startTimer();
        }}

        function markComplete() {{
            {min_time_check}
            if (confirm('Are you sure you want to mark this course as complete?\\n\\nTotal time: ' + formatTime(totalSeconds))) {{
                pauseTimer();
                commitTimeToScorm();
                SCORM.complete();
                updateStatus('Completed', true);
                alert('Course has been marked as complete!\\nTotal time recorded: ' + formatTime(totalSeconds));
            }}
        }}

        function exitCourse() {{
            var statusValue = document.getElementById('statusValue').textContent;

            if (statusValue !== 'Completed') {{
                if (!confirm('You have not marked the course as complete.\\nYour time (' + formatTime(totalSeconds) + ') will be saved.\\n\\nAre you sure you want to exit?')) {{
                    return;
                }}
            }}

            pauseTimer();
            commitTimeToScorm();

            if (courseWindow && !courseWindow.closed) {{
                courseWindow.close();
            }}

            SCORM.finish();
            window.close();

            setTimeout(function() {{
                alert('Please close this window to return to your LMS.');
            }}, 500);
        }}

        function updateStatus(status, isCompleted) {{
            var statusElement = document.getElementById('statusValue');
            statusElement.textContent = status;

            if (isCompleted) {{
                statusElement.classList.add('completed');
            }}
        }}

        document.addEventListener('visibilitychange', function() {{
            if (!document.hidden) {{
                if (document.getElementById('courseOpened').classList.contains('show') && !isTimerRunning) {{
                    startTimer();
                }}
            }}
        }});

        window.addEventListener('load', function() {{
            setTimeout(function() {{
                if (SCORM.isInitialized) {{
                    loadTimeFromScorm();

                    var prevStatus = SCORM.getValue('cmi.core.lesson_status');
                    if (prevStatus === 'completed' || prevStatus === 'passed') {{
                        updateStatus('Completed', true);
                        document.getElementById('initialState').classList.add('hide');
                        document.getElementById('courseOpened').classList.add('show');
                    }} else if (prevStatus === 'incomplete') {{
                        updateStatus('In Progress');
                        document.getElementById('initialState').classList.add('hide');
                        document.getElementById('courseOpened').classList.add('show');
                        startTimer();
                    }}
                }}
                updateTimerDisplay();
            }}, 500);
        }});

        window.addEventListener('beforeunload', function() {{
            pauseTimer();
            commitTimeToScorm();
        }});
    </script>
</body>
</html>'''

def create_scorm_package(course_title: str, course_url: str, primary_color: str,
                         mastery_score: int, expected_duration: int,
                         require_min_time: bool, min_time_minutes: int,
                         subtitle: str = "", additional_info: str = "") -> bytes:
    """Create a SCORM 1.2 package as a ZIP file in memory."""

    course_id = sanitize_filename(course_title)

    # Create ZIP in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add manifest
        manifest = generate_manifest(course_id, course_title, mastery_score)
        zip_file.writestr('imsmanifest.xml', manifest)

        # Add SCORM API
        scorm_api = generate_scorm_api()
        zip_file.writestr('scormapi.js', scorm_api)

        # Add HTML
        html = generate_html(course_title, course_url, primary_color,
                            expected_duration, require_min_time, min_time_minutes,
                            subtitle, additional_info)
        zip_file.writestr('index.html', html)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# ============================================
# STREAMLIT UI
# ============================================

st.title("📦 SCORM Package Generator")
st.markdown("Create SCORM 1.2 packages that embed external URLs with built-in time tracking.")

st.divider()

# Course Information Section
st.header("Course Information")

course_title = st.text_input(
    "Course Title",
    placeholder="e.g., Selling the Message®",
    help="The name that will appear in your LMS"
)

subtitle = st.text_input(
    "Subtitle (Optional)",
    placeholder="e.g., External Course with Time Tracking",
    help="A brief description that appears below the title"
)

additional_info = st.text_area(
    "Additional Information (Optional)",
    placeholder="Add any additional details, instructions, or information you want to display...",
    help="This will appear in a highlighted box on the course page. Supports line breaks.",
    height=100
)

course_url = st.text_input(
    "Course URL",
    placeholder="https://example.com/course",
    help="The external URL to embed in the SCORM package"
)

# Appearance Section
st.header("Appearance")

col1, col2 = st.columns(2)

with col1:
    primary_color = st.color_picker(
        "Primary Color",
        value="#5F2EEA",
        help="Main color for buttons and accents (SentinelOne purple by default)"
    )

with col2:
    expected_duration = st.number_input(
        "Expected Duration (minutes)",
        min_value=5,
        max_value=480,
        value=60,
        help="Used for the progress bar (100% = this duration)"
    )

# SCORM Settings Section
st.header("SCORM Settings")

col3, col4 = st.columns(2)

with col3:
    mastery_score = st.slider(
        "Mastery Score",
        min_value=0,
        max_value=100,
        value=80,
        help="Minimum score required to pass"
    )

with col4:
    require_min_time = st.checkbox(
        "Require Minimum Time",
        value=False,
        help="Prevent completion until minimum time is spent"
    )

if require_min_time:
    min_time_minutes = st.number_input(
        "Minimum Time Required (minutes)",
        min_value=1,
        max_value=480,
        value=30,
        help="Learner must spend at least this much time before marking complete"
    )
else:
    min_time_minutes = 0

st.divider()

# Validation and Generation
if st.button("🚀 Generate SCORM Package", type="primary", use_container_width=True):
    # Validate inputs
    errors = []

    if not course_title.strip():
        errors.append("Course title is required")

    if not course_url.strip():
        errors.append("Course URL is required")
    elif not course_url.startswith(('http://', 'https://')):
        errors.append("Course URL must start with http:// or https://")

    if errors:
        for error in errors:
            st.error(error)
    else:
        # Generate package
        with st.spinner("Generating SCORM package..."):
            try:
                zip_data = create_scorm_package(
                    course_title=course_title.strip(),
                    course_url=course_url.strip(),
                    primary_color=primary_color,
                    mastery_score=mastery_score,
                    expected_duration=expected_duration,
                    require_min_time=require_min_time,
                    min_time_minutes=min_time_minutes,
                    subtitle=subtitle.strip(),
                    additional_info=additional_info.strip()
                )

                filename = f"{sanitize_filename(course_title)}_SCORM.zip"

                st.success("✅ SCORM package generated successfully!")

                st.download_button(
                    label="📥 Download SCORM Package",
                    data=zip_data,
                    file_name=filename,
                    mime="application/zip",
                    use_container_width=True
                )

                # Show package info
                st.markdown(f"""
                <div class="info-box">
                    <strong>Package Details:</strong><br>
                    • Filename: <code>{filename}</code><br>
                    • SCORM Version: 1.2<br>
                    • Size: {len(zip_data) / 1024:.1f} KB<br>
                    • Files: imsmanifest.xml, index.html, scormapi.js
                </div>
                """, unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Error generating package: {str(e)}")

# Footer with instructions
st.divider()
with st.expander("ℹ️ How to Use"):
    st.markdown("""
    **Creating a Package:**
    1. Enter your course title and the external URL you want to embed
    2. Customize the appearance and SCORM settings
    3. Click "Generate SCORM Package"
    4. Download the ZIP file

    **Uploading to Your LMS:**
    1. Go to your LMS course management area
    2. Add a new SCORM/SCORM 1.2 activity
    3. Upload the downloaded ZIP file
    4. Configure any additional LMS-specific settings

    **How It Works:**
    - The package creates a launcher page that opens your external course in a new tab
    - Time tracking runs while the launcher window is open
    - Learners click "Mark Complete" when finished
    - Time and completion status are reported to your LMS via SCORM

    **Note:** External sites with iframe restrictions (X-Frame-Options) will open in a new tab
    instead of being embedded. This is normal and the time tracking still works.
    """)
