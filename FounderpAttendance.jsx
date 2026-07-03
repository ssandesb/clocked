import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Clock,
  RefreshCw,
  Bell,
  User,
  PanelLeft,
  Sparkles,
  LogOut,
  Mail,
  Lock,
  Eye,
  EyeOff,
  Zap,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Wand2,
} from "lucide-react";

/* ============================================================================
   DEMO AUTH — hardcoded on purpose for local testing.
   Swap this out for a real auth provider before shipping.
   ============================================================================ */
const DEMO_EMAIL = "bajracharyasandeshh@gmail.com";
const DEMO_PASSWORD = "bajracharyasandeshh@gmail.com";
const SESSION_DURATION_MS = 5 * 60 * 1000; // session breaks every 5 minutes

/* ============================================================================
   SHIFT RULES
   ============================================================================ */
const SHIFT_START_MIN = 9 * 60; // 09:00
const GRACE_MINUTES = 15;
const SHIFT_END_MIN = 18 * 60; // 18:00

/* ============================================================================
   BIKRAM SAMBAT (Nepali) CALENDAR — real conversion, not a placeholder.
   Table covers BS 2070–2099 (~AD 2013–2043). Reference epoch: BS 2070-01-01
   = AD 2013-04-14. Source: official Nepali panchanga month-length data.
   ============================================================================ */
const BS_DATA = {
  2070: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30],
  2071: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
  2072: [31, 32, 31, 32, 31, 30, 30, 29, 30, 29, 30, 30],
  2073: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
  2074: [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30],
  2075: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
  2076: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
  2077: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
  2078: [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30],
  2079: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
  2080: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
  2081: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
  2082: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
  2083: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
  2084: [31, 31, 32, 31, 31, 30, 30, 30, 29, 30, 30, 30],
  2085: [31, 32, 31, 32, 30, 31, 30, 30, 29, 30, 30, 30],
  2086: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
  2087: [31, 31, 32, 31, 31, 31, 30, 30, 29, 30, 30, 30],
  2088: [30, 31, 32, 32, 30, 31, 30, 30, 29, 30, 30, 30],
  2089: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
  2090: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
  2091: [31, 31, 32, 31, 31, 31, 30, 30, 29, 30, 30, 30],
  2092: [30, 31, 32, 32, 31, 30, 30, 30, 29, 30, 30, 30],
  2093: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
  2094: [31, 31, 32, 31, 31, 30, 30, 30, 29, 30, 30, 30],
  2095: [31, 31, 32, 31, 31, 31, 30, 29, 30, 30, 30, 30],
  2096: [30, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
  2097: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
  2098: [31, 31, 32, 31, 31, 31, 29, 30, 29, 30, 29, 31],
  2099: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
};
const NEPALI_EPOCH_MS = Date.UTC(2013, 3, 14); // BS 2070-01-01
const NEPALI_EPOCH_YEAR = 2070;
const NEPALI_MONTHS = [
  "Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashoj",
  "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
];
const KATHMANDU_TZ = "Asia/Kathmandu";

function yearTotal(y) {
  return BS_DATA[y] ? BS_DATA[y].reduce((a, b) => a + b, 0) : null;
}

// Converts an AD calendar day (as seen in Nepal) into a BS date.
function adToBs(year, month, day) {
  if (year < NEPALI_EPOCH_YEAR - 1 || !BS_DATA[NEPALI_EPOCH_YEAR]) return null;
  const utcMs = Date.UTC(year, month - 1, day);
  let daysPassed = Math.round((utcMs - NEPALI_EPOCH_MS) / 86400000) + 1;
  let bsYear = NEPALI_EPOCH_YEAR;
  while (daysPassed < 1) {
    bsYear -= 1;
    const total = yearTotal(bsYear);
    if (total === null) return null;
    daysPassed += total;
  }
  while (true) {
    const total = yearTotal(bsYear);
    if (total === null) return null;
    if (daysPassed <= total) break;
    daysPassed -= total;
    bsYear += 1;
  }
  let bsMonth = 0;
  for (let i = 0; i < 12; i++) {
    if (daysPassed <= BS_DATA[bsYear][i]) {
      bsMonth = i;
      break;
    }
    daysPassed -= BS_DATA[bsYear][i];
  }
  return { year: bsYear, month: bsMonth + 1, day: daysPassed };
}

// Reads the current wall-clock time in Nepal (Asia/Kathmandu), regardless of
// the visitor's own device time zone — this is the "real time zone data" feed.
function getKathmanduParts(date) {
  const dtf = new Intl.DateTimeFormat("en-US", {
    timeZone: KATHMANDU_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    weekday: "short",
  });
  const map = {};
  dtf.formatToParts(date).forEach((p) => (map[p.type] = p.value));
  return {
    year: parseInt(map.year, 10),
    month: parseInt(map.month, 10),
    day: parseInt(map.day, 10),
    hour: map.hour === "24" ? 0 : parseInt(map.hour, 10),
    minute: parseInt(map.minute, 10),
    second: parseInt(map.second, 10),
    weekday: map.weekday,
  };
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

function formatClock(parts) {
  return `${pad2(parts.hour)}:${pad2(parts.minute)}:${pad2(parts.second)}`;
}

function formatBsLine(parts) {
  const bs = adToBs(parts.year, parts.month, parts.day);
  if (!bs) return `${parts.weekday}, ${parts.year}-${pad2(parts.month)}-${pad2(parts.day)}`;
  return `${parts.weekday}, ${NEPALI_MONTHS[bs.month - 1]} ${bs.day}, ${bs.year}`;
}

function minutesOfDay(parts) {
  return parts.hour * 60 + parts.minute;
}

function getClockInStatus(minOfDay) {
  if (minOfDay <= SHIFT_START_MIN) return { label: "On Time", tone: "green" };
  if (minOfDay <= SHIFT_START_MIN + GRACE_MINUTES) return { label: "Late (With Grace)", tone: "amber" };
  return { label: "Late", tone: "red" };
}

function formatHm(parts) {
  return `${pad2(parts.hour)}:${pad2(parts.minute)}`;
}

function hoursBetween(startParts, endParts) {
  const startMin = startParts.hour * 60 + startParts.minute + startParts.second / 60;
  const endMin = endParts.hour * 60 + endParts.minute + endParts.second / 60;
  let diff = endMin - startMin;
  if (diff < 0) diff += 24 * 60;
  const h = Math.floor(diff / 60);
  const m = Math.round(diff % 60);
  return `${h}h ${pad2(m)}m`;
}

/* ============================================================================
   SHARED UI BITS
   ============================================================================ */
const TONE_STYLES = {
  green: "bg-emerald-50 text-emerald-700 border-emerald-200",
  amber: "bg-amber-50 text-amber-700 border-amber-200",
  red: "bg-red-50 text-red-700 border-red-200",
  blue: "bg-blue-50 text-blue-700 border-blue-200",
  gray: "bg-gray-100 text-gray-600 border-gray-200",
};

function Badge({ tone = "gray", children }) {
  return (
    <span
      className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium border ${TONE_STYLES[tone]}`}
    >
      {children}
    </span>
  );
}

function Logo() {
  return (
    <div className="flex items-center gap-2">
      <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-sm">
        F
      </div>
      <span className="font-bold text-lg text-gray-900" style={{ fontFamily: "'Poppins', sans-serif" }}>
        Founderp
      </span>
    </div>
  );
}

/* ============================================================================
   LANDING PAGE  —  route: "/"
   ============================================================================ */
function LandingPage({ navigate }) {
  return (
    <div className="min-h-full bg-white" style={{ fontFamily: "'Inter', sans-serif" }}>
      <header className="border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Logo />
          <nav className="hidden md:flex items-center gap-8 text-sm text-gray-600">
            <span className="cursor-default hover:text-gray-900 transition">Features</span>
            <span className="cursor-default hover:text-gray-900 transition">Pricing</span>
            <span className="cursor-default hover:text-gray-900 transition">About</span>
            <span className="cursor-default hover:text-gray-900 transition">Contact</span>
          </nav>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/login")}
              className="px-4 py-2 rounded-lg text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 transition"
            >
              Sign in
            </button>
            <button
              onClick={() => navigate("/login")}
              className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 transition"
            >
              Start Free Trial
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 pt-24 pb-32 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-gray-200 text-sm text-gray-700 mb-8">
          <Zap className="w-4 h-4" />
          Built for founders who move fast
        </div>
        <h1 className="text-5xl md:text-6xl font-extrabold text-gray-900 leading-tight tracking-tight">
          Your entire business.
          <br />
          <span className="text-indigo-600">One operating system.</span>
        </h1>
        <p className="mt-6 text-lg text-gray-500 max-w-2xl mx-auto leading-relaxed">
          Founderp unifies HR, finance, projects, sales, compliance and 25+ modules
          into a single platform — so you can stop juggling tools and start scaling.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4">
          <button
            onClick={() => navigate("/login")}
            className="px-6 py-3 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 transition inline-flex items-center gap-2"
          >
            Sign in to your workspace
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
        <p className="mt-4 text-xs text-gray-400">
          Demo build — sign-in is pre-wired with a test account for local development.
        </p>
      </main>
    </div>
  );
}

/* ============================================================================
   LOGIN PAGE  —  route: "/login"
   ============================================================================ */
function LoginPage({ navigate, onLogin, sessionExpired, clearSessionExpired }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = () => {
    clearSessionExpired();
    if (email.trim() === DEMO_EMAIL && password === DEMO_PASSWORD) {
      setError("");
      onLogin();
      navigate("/user/attendance");
    } else {
      setError("Invalid email or password. Try the demo credentials below.");
    }
  };

  const fillDemo = () => {
    setEmail(DEMO_EMAIL);
    setPassword(DEMO_PASSWORD);
    setError("");
  };

  return (
    <div
      className="min-h-full bg-gray-50 flex flex-col items-center justify-center px-6 py-16"
      style={{ fontFamily: "'Inter', sans-serif" }}
    >
      <button onClick={() => navigate("/")} className="mb-8">
        <Logo />
      </button>

      <div className="w-full max-w-sm bg-white rounded-2xl border border-gray-200 shadow-sm p-8">
        <h1 className="text-2xl font-bold text-gray-900 text-center">Sign In</h1>
        <p className="mt-1 text-sm text-gray-500 text-center">
          Enter your credentials to access your account
        </p>

        {sessionExpired && (
          <div className="mt-5 flex items-start gap-2 px-3 py-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>Your session ended after 5 minutes. Please sign in again.</span>
          </div>
        )}

        <div className="mt-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Email</label>
            <div className="relative">
              <Mail className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                className="w-full pl-9 pr-3 py-2.5 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Password</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                placeholder="Enter your password"
                className="w-full pl-9 pr-9 py-2.5 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 text-xs text-red-600">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <button
            onClick={handleSubmit}
            className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold transition"
          >
            Sign In
          </button>

          <button
            onClick={fillDemo}
            className="w-full py-2.5 rounded-lg border border-dashed border-indigo-300 text-indigo-600 text-xs font-medium hover:bg-indigo-50 transition inline-flex items-center justify-center gap-1.5"
          >
            <Wand2 className="w-3.5 h-3.5" />
            Use demo credentials
          </button>
        </div>

        <div className="mt-6 text-center text-sm text-gray-500">
          Don't have an account? <span className="text-indigo-600 cursor-default">Sign Up</span>
        </div>
        <div className="mt-2 text-center">
          <span className="text-sm text-indigo-600 cursor-default">Forgot Password?</span>
        </div>
      </div>

      <p className="mt-6 text-xs text-gray-400 text-center max-w-xs">
        Demo credentials — email and password are both{" "}
        <code className="text-gray-500">{DEMO_EMAIL}</code>
      </p>
    </div>
  );
}

/* ============================================================================
   ATTENDANCE PAGE  —  route: "/user/attendance"
   ============================================================================ */
function AttendancePage({ navigate, onLogout, now, sessionMsRemaining }) {
  const [clockedIn, setClockedIn] = useState(false);
  const [clockInParts, setClockInParts] = useState(null);
  const [clockOutParts, setClockOutParts] = useState(null);
  const [notes, setNotes] = useState("");
  const [ipStatus, setIpStatus] = useState("loading"); // loading | done | error
  const [ip, setIp] = useState("");
  const [activeTab, setActiveTab] = useState("today");

  const nowParts = getKathmanduParts(now);

  const fetchIp = useCallback(() => {
    setIpStatus("loading");
    let cancelled = false;
    const timeout = setTimeout(() => {
      if (!cancelled) {
        setIpStatus("error");
      }
    }, 4000);

    fetch("https://api.ipify.org?format=json")
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        clearTimeout(timeout);
        setIp(data.ip);
        setIpStatus("done");
      })
      .catch(() => {
        if (cancelled) return;
        clearTimeout(timeout);
        setIpStatus("error");
      });

    return () => {
      cancelled = true;
      clearTimeout(timeout);
    };
  }, []);

  useEffect(() => {
    const cleanup = fetchIp();
    return cleanup;
  }, [fetchIp]);

  const handleClockIn = () => {
    setClockInParts(nowParts);
    setClockOutParts(null);
    setClockedIn(true);
  };

  const handleClockOut = () => {
    setClockOutParts(nowParts);
    setClockedIn(false);
  };

  const handleStartNewSession = () => {
    setClockInParts(null);
    setClockOutParts(null);
    setNotes("");
  };

  const status = clockInParts ? getClockInStatus(minutesOfDay(clockInParts)) : null;
  const sessionMinsLeft = Math.max(0, Math.ceil(sessionMsRemaining / 60000));

  return (
    <div className="min-h-full bg-gray-50" style={{ fontFamily: "'Inter', sans-serif" }}>
      {/* Top bar */}
      <div className="bg-white border-b border-gray-200">
        <div className="px-6 h-16 flex items-center justify-between">
          <button className="w-9 h-9 flex items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition">
            <PanelLeft className="w-4 h-4" />
          </button>
          <div className="flex items-center gap-4">
            <Badge tone={sessionMinsLeft <= 1 ? "red" : "gray"}>
              Session resets in {sessionMinsLeft}m
            </Badge>
            <Sparkles className="w-4 h-4 text-amber-500" />
            <div className="relative">
              <Bell className="w-4 h-4 text-gray-500" />
              <span className="absolute -top-1.5 -right-1.5 bg-red-500 text-white text-[10px] leading-none rounded-full w-4 h-4 flex items-center justify-center">
                3
              </span>
            </div>
            <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center">
              <User className="w-4 h-4" />
            </div>
            <div className="text-right leading-tight">
              <div className="text-sm font-medium text-gray-900">Sandesh Bajracharya</div>
              <div className="text-xs text-gray-400">Employee</div>
            </div>
            <button
              onClick={() => {
                onLogout();
                navigate("/login");
              }}
              className="w-9 h-9 flex items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition"
              title="Log out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-gray-900">Attendance Module</h1>

        {/* Tabs */}
        <div className="mt-5 grid grid-cols-3 gap-2 bg-gray-100 rounded-xl p-1 max-w-xl">
          {[
            { key: "today", label: "Today's Attendance" },
            { key: "calendar", label: "Calendar View" },
            { key: "history", label: "Attendance History" },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`py-2 rounded-lg text-sm font-medium transition ${
                activeTab === tab.key
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab !== "today" ? (
          <div className="mt-6 bg-white rounded-xl border border-gray-200 p-16 text-center text-gray-400 text-sm">
            {activeTab === "calendar" ? "Calendar View" : "Attendance History"} isn't wired up in
            this demo — only Today's Attendance is functional.
          </div>
        ) : (
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Clock In/Out card */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-gray-900 font-semibold">
                  <Clock className="w-4 h-4" />
                  Clock In/Out
                </div>
                <button
                  onClick={fetchIp}
                  className="text-gray-400 hover:text-gray-600 transition"
                  title="Refresh"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>

              <div className="mt-4 bg-gray-50 rounded-lg py-6 text-center">
                <div className="text-3xl font-bold text-gray-900 tabular-nums">
                  {formatClock(nowParts)}
                </div>
                <div className="mt-1 text-sm text-gray-500">{formatBsLine(nowParts)}</div>
              </div>

              <div className="mt-4 bg-gray-50 rounded-lg px-4 py-3 flex items-center gap-2 text-sm text-gray-600">
                {ipStatus === "loading" && (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-gray-400" />
                    <div>
                      <div>Getting IP Address...</div>
                      <div className="text-xs text-gray-400">Please wait</div>
                    </div>
                  </>
                )}
                {ipStatus === "done" && (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    <span>
                      IP Address: <span className="font-medium text-gray-800">{ip}</span>
                    </span>
                  </>
                )}
                {ipStatus === "error" && (
                  <>
                    <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                    <span>Couldn't detect IP address on this network</span>
                  </>
                )}
              </div>

              <div className="mt-4">
                <label className="block text-sm text-gray-700 mb-1.5">Notes (Optional)</label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Add any notes about your attendance..."
                  rows={2}
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
                />
              </div>

              <div className="mt-4">
                {!clockInParts && (
                  <button
                    onClick={handleClockIn}
                    className="w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold transition inline-flex items-center justify-center gap-2"
                  >
                    <Clock className="w-4 h-4" />
                    Clock In
                  </button>
                )}
                {clockedIn && clockInParts && (
                  <button
                    onClick={handleClockOut}
                    className="w-full py-3 rounded-lg border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm font-medium transition inline-flex items-center justify-center gap-2"
                  >
                    <Clock className="w-4 h-4" />
                    Clock Out
                  </button>
                )}
                {!clockedIn && clockInParts && clockOutParts && (
                  <button
                    onClick={handleStartNewSession}
                    className="w-full py-3 rounded-lg border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm font-medium transition"
                  >
                    Start New Session
                  </button>
                )}
              </div>

              <div className="mt-4 text-xs text-gray-400 space-y-0.5">
                <div>Shift Start: 09:00</div>
                <div>Grace Period: {GRACE_MINUTES} minutes</div>
                <div>Shift End: 18:00</div>
              </div>
            </div>

            {/* Today's status card */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-gray-900 font-semibold">
                  <Clock className="w-4 h-4" />
                  Today's Status
                </div>
                <RefreshCw className="w-4 h-4 text-gray-300" />
              </div>

              <div className="mt-5 space-y-4 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Status</span>
                  <div className="flex items-center gap-2">
                    {!clockInParts && <Badge tone="gray">Not Clocked In</Badge>}
                    {clockInParts && status && <Badge tone={status.tone}>{status.label}</Badge>}
                    {clockedIn && <Badge tone="blue">Currently Working</Badge>}
                    {!clockedIn && clockInParts && clockOutParts && (
                      <Badge tone="green">Completed</Badge>
                    )}
                  </div>
                </div>

                {clockInParts && (
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Clock In</span>
                    <span className="font-medium text-gray-900 tabular-nums">
                      {formatHm(clockInParts)}
                    </span>
                  </div>
                )}

                {clockOutParts && (
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Clock Out</span>
                    <span className="font-medium text-gray-900 tabular-nums">
                      {formatHm(clockOutParts)}
                    </span>
                  </div>
                )}

                {clockInParts && clockOutParts && (
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Total Hours</span>
                    <span className="font-medium text-gray-900">
                      {hoursBetween(clockInParts, clockOutParts)}
                    </span>
                  </div>
                )}

                {notes && clockInParts && (
                  <div className="pt-2 border-t border-gray-100">
                    <span className="text-gray-500 block mb-1">Notes</span>
                    <span className="text-gray-700">{notes}</span>
                  </div>
                )}

                {!clockInParts && (
                  <p className="text-gray-400 text-sm pt-2">
                    Clock in to see your status for today.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ============================================================================
   APP  —  in-memory routing across "/", "/login", "/user/attendance"
   (No react-router in this sandbox, so routing is state-driven. Swap `route`
   state + `navigate()` for real react-router calls when this leaves the demo.)
   ============================================================================ */
export default function App() {
  const [route, setRoute] = useState("/");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [now, setNow] = useState(new Date());
  const loginTimeRef = useRef(null);
  const logoutTimerRef = useRef(null);

  // Real-time clock, ticking once a second.
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const navigate = (path) => setRoute(path);

  const clearSession = useCallback(() => {
    setIsAuthenticated(false);
    loginTimeRef.current = null;
    if (logoutTimerRef.current) {
      clearTimeout(logoutTimerRef.current);
      logoutTimerRef.current = null;
    }
  }, []);

  const handleLogin = useCallback(() => {
    setIsAuthenticated(true);
    setSessionExpired(false);
    loginTimeRef.current = Date.now();
    if (logoutTimerRef.current) clearTimeout(logoutTimerRef.current);
    logoutTimerRef.current = setTimeout(() => {
      clearSession();
      setSessionExpired(true);
      setRoute("/login");
    }, SESSION_DURATION_MS);
  }, [clearSession]);

  const handleLogout = useCallback(() => {
    clearSession();
    setSessionExpired(false);
  }, [clearSession]);

  // Guard the attendance route.
  useEffect(() => {
    if (route === "/user/attendance" && !isAuthenticated) {
      setRoute("/login");
    }
  }, [route, isAuthenticated]);

  useEffect(() => {
    return () => {
      if (logoutTimerRef.current) clearTimeout(logoutTimerRef.current);
    };
  }, []);

  const sessionMsRemaining = loginTimeRef.current
    ? Math.max(0, SESSION_DURATION_MS - (now.getTime() - loginTimeRef.current))
    : SESSION_DURATION_MS;

  return (
    <div className="min-h-screen w-full">
      {route === "/" && <LandingPage navigate={navigate} />}
      {route === "/login" && (
        <LoginPage
          navigate={navigate}
          onLogin={handleLogin}
          sessionExpired={sessionExpired}
          clearSessionExpired={() => setSessionExpired(false)}
        />
      )}
      {route === "/user/attendance" && isAuthenticated && (
        <AttendancePage
          navigate={navigate}
          onLogout={handleLogout}
          now={now}
          sessionMsRemaining={sessionMsRemaining}
        />
      )}
    </div>
  );
}
