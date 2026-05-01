let token = localStorage.getItem("rh_meet_token") || "";
let currentUser = null;
let meetings = [];
let adminUsers = [];
let currentMeetingId = null;
let pendingSharedRoom = null;
let jitsiApi = null;

const $ = id => document.getElementById(id);
const navButtons = () => document.querySelectorAll(".nav-btn");
const openButtons = () => document.querySelectorAll("[data-open]");

async function api(path, options = {}) {
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, {...options, headers});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.detail || "Request failed");
  return data;
}

function showLogin() {
  $("loginPage").classList.remove("hidden");
  $("appPage").classList.add("hidden");
}

function showApp() {
  $("loginPage").classList.add("hidden");
  $("appPage").classList.remove("hidden");
  $("userName").innerText = currentUser.name;
  $("userRole").innerText = currentUser.role;
  $("meetingHost").value = currentUser.name;
  document.querySelectorAll(".admin-only").forEach(el => el.classList.toggle("hidden", currentUser.role !== "admin"));
}

async function login() {
  $("loginError").innerText = "";
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({email: $("emailInput").value.trim(), password: $("passwordInput").value})
    });
    token = data.token;
    currentUser = data.user;
    localStorage.setItem("rh_meet_token", token);
    showApp();
    await loadMeetings();
    const sharedRoom = detectSharedRoomFromUrl();
    if (sharedRoom) {
      showView("join");
      showSharedRoomPrompt(sharedRoom);
    } else {
      showView("home");
    }
  } catch (e) {
    $("loginError").innerText = e.message;
  }
}

async function logout() {
  try { await api("/api/logout", {method: "POST"}); } catch {}
  token = "";
  currentUser = null;
  localStorage.removeItem("rh_meet_token");
  destroyJitsi();
  showLogin();
}

async function checkSession() {
  if (!token) return showLogin();
  try {
    const data = await api("/api/me");
    currentUser = data.user;
    showApp();
    await loadMeetings();
    const sharedRoom = detectSharedRoomFromUrl();
    if (sharedRoom) {
      showView("join");
      showSharedRoomPrompt(sharedRoom);
    } else {
      showView("home");
    }
  } catch {
    localStorage.removeItem("rh_meet_token");
    token = "";
    showLogin();
  }
}

function formatDateTime(date, time) {
  if (!date && !time) return "Instant meeting";
  return `${date || ""} ${time || ""}`.trim();
}

function makeShareLink(roomId) {
  const url = new URL(window.location.origin);
  url.searchParams.set("room", roomId);
  return url.toString();
}

function detectSharedRoomFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const room = params.get("room");
  pendingSharedRoom = room ? decodeURIComponent(room) : null;
  return pendingSharedRoom;
}

function showSharedRoomPrompt(roomId) {
  if (!roomId || !$("sharedLinkBox")) return;
  $("sharedLinkBox").classList.remove("hidden");
  $("sharedLinkText").innerText = roomId;
  $("joinRoomInput").value = roomId;
}

function showView(viewId) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  $(viewId).classList.add("active");
  navButtons().forEach(btn => btn.classList.toggle("active", btn.dataset.view === viewId));
  const title = {
    home: "Home", schedule: "Schedule Meeting", join: "Join Meeting",
    meetings: "My Meetings", admin: "Admin Dashboard", meetingRoom: "Live Meeting Room"
  }[viewId] || "Reap Holding Online Meet";
  $("pageTitle").innerText = title;
  if (viewId !== "meetingRoom") destroyJitsi();
  renderAll();
}

async function loadMeetings() {
  const data = await api("/api/meetings");
  meetings = data.meetings || [];
  renderAll();
}

async function saveMeeting(startNow = false) {
  $("scheduleError").innerText = "";
  const title = $("meetingTitle").value.trim();
  const host = $("meetingHost").value.trim() || currentUser.name;
  if (!title || !host) {
    $("scheduleError").innerText = "اكتب عنوان الاجتماع واسم الـ Host.";
    return;
  }

  try {
    const data = await api("/api/meetings", {
      method: "POST",
      body: JSON.stringify({
        title,
        department: $("meetingDepartment").value,
        meeting_date: $("meetingDate").value,
        meeting_time: $("meetingTime").value,
        duration: Number($("meetingDuration").value),
        host_name: host,
        participants: $("meetingParticipants").value.trim(),
        agenda: $("meetingAgenda").value.trim(),
        status: startNow ? "Live" : "Scheduled"
      })
    });
    clearScheduleForm();
    await loadMeetings();
    if (startNow) openMeetingRoom(data.meeting.room_id);
    else {
      alert(`Meeting saved. Meeting ID: ${data.meeting.room_id}`);
      showView("meetings");
    }
  } catch (e) {
    $("scheduleError").innerText = e.message;
  }
}

function clearScheduleForm() {
  $("meetingTitle").value = "";
  $("meetingHost").value = currentUser ? currentUser.name : "";
  $("meetingParticipants").value = "";
  $("meetingAgenda").value = "";
}

async function startInstantMeeting() {
  const data = await api("/api/meetings", {
    method: "POST",
    body: JSON.stringify({
      title: "Instant Reap Holding Meeting",
      department: currentUser.department || "Management",
      meeting_date: new Date().toISOString().slice(0, 10),
      meeting_time: new Date().toTimeString().slice(0, 5),
      duration: 60,
      host_name: currentUser.name,
      participants: "",
      agenda: "Instant meeting",
      status: "Live"
    })
  });
  await loadMeetings();
  openMeetingRoom(data.meeting.room_id);
}

async function joinMeeting() {
  const id = $("joinRoomInput").value.trim();
  if (!id) return alert("Enter Meeting ID first.");

  try {
    await api(`/api/meetings/${encodeURIComponent(id)}`);
    openMeetingRoom(id);
  } catch (e) {
    alert("Meeting ID not found. Please check the shared link or meeting ID.");
  }
}

async function openMeetingRoom(id) {
  const data = await api(`/api/meetings/${encodeURIComponent(id)}`);
  const meeting = data.meeting;
  currentMeetingId = id;
  await api(`/api/meetings/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({status: "Live"})
  });
  meeting.status = "Live";

  $("liveMeetingTitle").innerText = meeting.title;
  $("liveMeetingMeta").innerText = `${meeting.department} • ${formatDateTime(meeting.meeting_date, meeting.meeting_time)} • ${meeting.duration} minutes`;
  $("roomIdText").innerText = meeting.room_id;
  $("meetingNotes").value = meeting.notes || "";
  showView("meetingRoom");
  setTimeout(() => startJitsi(meeting), 150);
}

function startJitsi(meeting) {
  destroyJitsi();
  const container = $("jitsiContainer");
  if (!window.JitsiMeetExternalAPI) {
    container.innerHTML = `<div class="loading-room"><div><span>⚠️</span><strong>Jitsi script could not load</strong><p>Check internet connection, then refresh.</p></div></div>`;
    return;
  }
  container.innerHTML = "";
  jitsiApi = new JitsiMeetExternalAPI("meet.jit.si", {
    roomName: meeting.room_id,
    width: "100%",
    height: "100%",
    parentNode: container,
    userInfo: {displayName: currentUser.name},
    configOverwrite: {prejoinPageEnabled: true, startWithAudioMuted: true},
    interfaceConfigOverwrite: {SHOW_JITSI_WATERMARK: false, SHOW_WATERMARK_FOR_GUESTS: false, DEFAULT_BACKGROUND: "#020617"}
  });
}

function destroyJitsi() {
  if (jitsiApi) {
    jitsiApi.dispose();
    jitsiApi = null;
  }
}

async function saveNotes() {
  if (!currentMeetingId) return;
  await api(`/api/meetings/${encodeURIComponent(currentMeetingId)}`, {
    method: "PATCH",
    body: JSON.stringify({notes: $("meetingNotes").value.trim()})
  });
  alert("Meeting notes saved.");
  await loadMeetings();
}

async function markCompleted() {
  if (!currentMeetingId) return;
  await api(`/api/meetings/${encodeURIComponent(currentMeetingId)}`, {
    method: "PATCH",
    body: JSON.stringify({status: "Completed", notes: $("meetingNotes").value.trim()})
  });
  destroyJitsi();
  await loadMeetings();
  showView("meetings");
}

function leaveMeeting() {
  destroyJitsi();
  showView("home");
}

function copyRoomId() {
  const text = $("roomIdText").innerText;
  navigator.clipboard.writeText(text).then(() => alert("Meeting ID copied.")).catch(() => alert(text));
}

function copyShareLink(roomId = null) {
  const id = roomId || $("roomIdText").innerText;
  const link = makeShareLink(id);
  navigator.clipboard.writeText(link).then(() => alert("Share link copied.")).catch(() => alert(link));
}

function openSharedMeeting() {
  const room = pendingSharedRoom || $("joinRoomInput").value.trim();
  if (!room) return alert("No shared meeting found.");
  $("joinRoomInput").value = room;
  joinMeeting();
}

async function deleteMeeting(id) {
  if (!confirm("Delete this meeting?")) return;
  await api(`/api/meetings/${encodeURIComponent(id)}`, {method: "DELETE"});
  await loadMeetings();
}

async function loadUsers() {
  if (!currentUser || currentUser.role !== "admin") return;
  try {
    const data = await api("/api/admin/users");
    adminUsers = data.users || [];
    renderUsers();
  } catch (e) {
    console.warn(e);
  }
}

async function createUser() {
  if (!currentUser || currentUser.role !== "admin") return;

  $("userCreateError").innerText = "";

  const payload = {
    name: $("newUserName").value.trim(),
    email: $("newUserEmail").value.trim(),
    password: $("newUserPassword").value,
    role: $("newUserRole").value,
    department: $("newUserDepartment").value
  };

  if (!payload.name || !payload.email || !payload.password) {
    $("userCreateError").innerText = "اكتب الاسم والإيميل والباسورد.";
    return;
  }

  try {
    await api("/api/admin/users", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    $("newUserName").value = "";
    $("newUserEmail").value = "";
    $("newUserPassword").value = "";
    $("newUserRole").value = "user";
    $("newUserDepartment").value = "General";

    await loadUsers();
    alert("User created successfully.");
  } catch (e) {
    $("userCreateError").innerText = e.message;
  }
}

async function deleteUser(userId) {
  if (!confirm("Delete this user?")) return;
  try {
    await api(`/api/admin/users/${userId}`, {method: "DELETE"});
    await loadUsers();
  } catch (e) {
    alert(e.message);
  }
}

function renderUsers() {
  const box = $("usersList");
  if (!box) return;

  if (!adminUsers.length) {
    box.innerHTML = `<p class="muted">No users found.</p>`;
    return;
  }

  box.innerHTML = adminUsers.map(u => `
    <div class="user-row">
      <strong>${escapeHtml(u.name)}</strong>
      <span>${escapeHtml(u.email)}</span>
      <small>${escapeHtml(u.role)}</small>
      <small>${escapeHtml(u.department)}</small>
      ${currentUser && currentUser.id === u.id
        ? `<button class="secondary" disabled>Current</button>`
        : `<button class="danger" onclick="deleteUser(${u.id})">Delete</button>`}
    </div>
  `).join("");
}

function renderMeetings() {
  const list = $("meetingsList");
  if (!list) return;
  if (!meetings.length) {
    list.innerHTML = `<div class="card"><p class="muted">No meetings yet. Schedule your first meeting.</p></div>`;
    return;
  }
  list.innerHTML = meetings.map(m => `
    <article class="meeting-item">
      <div class="meeting-item-top">
        <div>
          <h3>${escapeHtml(m.title)}</h3>
          <p class="muted">${escapeHtml(m.department)} • ${formatDateTime(m.meeting_date, m.meeting_time)} • ${m.duration} minutes</p>
          <p class="meeting-id">${escapeHtml(m.room_id)}</p>
        </div>
        <span class="badge">${escapeHtml(m.status)}</span>
      </div>
      <p class="muted"><strong>Host:</strong> ${escapeHtml(m.host_name)} ${m.created_by_name ? "• Created by: " + escapeHtml(m.created_by_name) : ""}</p>
      ${m.agenda ? `<p>${escapeHtml(m.agenda)}</p>` : ""}
      <div class="actions">
        <button class="primary" onclick="openMeetingRoom('${m.room_id}')">Start / Join</button>
        <button class="secondary" onclick="copyText('${m.room_id}')">Copy ID</button>
        <button class="primary" onclick="copyShareLink('${m.room_id}')">Copy Link</button>
        ${currentUser && currentUser.role === "admin" ? `<button class="danger" onclick="deleteMeeting('${m.room_id}')">Delete</button>` : ""}
      </div>
    </article>
  `).join("");
}

async function renderAdmin() {
  if (!currentUser || currentUser.role !== "admin") return;
  try {
    const data = await api("/api/admin/stats");
    $("adminTotal").innerText = data.total_meetings;
    $("adminHours").innerText = data.total_hours;
    $("adminDepartments").innerText = data.departments;
    const max = Math.max(...(data.usage || []).map(x => x.count), 1);
    $("departmentUsage").innerHTML = (data.usage || []).map(row => `
      <div class="usage-row">
        <strong>${escapeHtml(row.department)}</strong>
        <div class="bar"><span style="width:${(row.count / max) * 100}%"></span></div>
        <span>${row.count}</span>
      </div>
    `).join("") || `<p class="muted">No usage data yet.</p>`;
    $("recentMeetings").innerHTML = (data.recent || []).map(m => `
      <article class="meeting-item">
        <div class="meeting-item-top">
          <div><h3>${escapeHtml(m.title)}</h3><p class="muted">${escapeHtml(m.department)} • ${formatDateTime(m.meeting_date, m.meeting_time)}</p></div>
          <span class="badge">${escapeHtml(m.status)}</span>
        </div>
      </article>
    `).join("") || `<p class="muted">No meetings yet.</p>`;

    await loadUsers();
  } catch (e) {
    console.warn(e);
  }
}

function renderHomeStats() {
  $("homeTotalMeetings").innerText = meetings.length;
  $("homeScheduledMeetings").innerText = meetings.filter(m => m.status === "Scheduled").length;
  $("homeCompletedMeetings").innerText = meetings.filter(m => m.status === "Completed").length;
}

function renderAll() {
  if (!$("appPage") || $("appPage").classList.contains("hidden")) return;
  renderHomeStats();
  renderMeetings();
  renderAdmin();
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => alert("Copied."));
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, s => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[s]));
}

function initDates() {
  const today = new Date().toISOString().slice(0, 10);
  $("meetingDate").value = today;
  $("meetingTime").value = "10:00";
}

function bindEvents() {
  $("loginBtn").addEventListener("click", login);
  $("passwordInput").addEventListener("keydown", e => { if (e.key === "Enter") login(); });
  $("logoutBtn").addEventListener("click", logout);

  navButtons().forEach(btn => btn.addEventListener("click", () => showView(btn.dataset.view)));
  openButtons().forEach(btn => btn.addEventListener("click", () => showView(btn.dataset.open)));

  $("instantMeetingBtn").addEventListener("click", startInstantMeeting);
  $("saveMeetingBtn").addEventListener("click", () => saveMeeting(false));
  $("saveAndStartBtn").addEventListener("click", () => saveMeeting(true));
  $("joinMeetingBtn").addEventListener("click", joinMeeting);
  $("leaveMeetingBtn").addEventListener("click", leaveMeeting);
  $("markCompletedBtn").addEventListener("click", markCompleted);
  $("saveNotesBtn").addEventListener("click", saveNotes);
  $("copyRoomBtn").addEventListener("click", copyRoomId);
  $("copyShareLinkBtn").addEventListener("click", () => copyShareLink());
  $("openSharedMeetingBtn").addEventListener("click", openSharedMeeting);
  $("createUserBtn").addEventListener("click", createUser);
}

window.openMeetingRoom = openMeetingRoom;
window.deleteMeeting = deleteMeeting;
window.deleteUser = deleteUser;
window.copyShareLink = copyShareLink;
window.copyText = copyText;

initDates();
bindEvents();
checkSession();