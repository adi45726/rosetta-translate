import { initializeApp } from "https://www.gstatic.com/firebasejs/12.16.0/firebase-app.js";
import { getAuth, GoogleAuthProvider, onAuthStateChanged, signInWithPopup } from "https://www.gstatic.com/firebasejs/12.16.0/firebase-auth.js";
import { collection, getDocs, getFirestore, limit, orderBy, query } from "https://www.gstatic.com/firebasejs/12.16.0/firebase-firestore.js";

const byId = (id) => document.getElementById(id);
const config = JSON.parse(byId("firebase-config-data").textContent);
const configured = Boolean(config.apiKey && config.authDomain && config.projectId && config.appId);
let auth = null;
let db = null;
let customerData = [];

function showError(message) { byId("admin-auth-error").textContent = message; }
function dateText(value) {
  if (!value) return "—";
  const date = value.toDate ? value.toDate() : value._seconds ? new Date(value._seconds * 1000) : new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : date.toLocaleString();
}
function escapeText(value) {
  const node = document.createElement("span");
  node.textContent = value ?? "";
  return node.innerHTML;
}
function renderCustomers(users) {
  byId("customer-table").innerHTML = users.map((user) => `<tr>
    <td><b>${escapeText(`${user.first_name || ""} ${user.last_name || ""}`.trim() || "Unnamed")}</b><small>${escapeText(user.email || user.uid)}</small></td>
    <td><span class="account-pill ${user.anonymous ? "guest" : ""}">${user.anonymous ? "Guest" : "Member"}</span></td>
    <td>${escapeText(user.purpose || "—")}</td><td>${escapeText(user.role || "—")}</td><td>${escapeText(user.frequency || "—")}</td>
  </tr>`).join("") || `<tr><td colspan="5">No customer profiles yet.</td></tr>`;
}
function render(data) {
  const metrics = data.metrics;
  byId("metric-users").textContent = metrics.total_users.toLocaleString();
  byId("metric-split").textContent = `${metrics.registered_users} members · ${metrics.guest_users} guests`;
  byId("metric-requests").textContent = metrics.requests.toLocaleString();
  byId("metric-speed").textContent = `${metrics.average_speed_ms} ms`;
  byId("metric-errors").textContent = metrics.requests ? `${((metrics.errors / metrics.requests) * 100).toFixed(1)}%` : "0%";
  const features = Object.entries(metrics.feature_counts).sort((a, b) => b[1] - a[1]);
  const max = features[0]?.[1] || 1;
  byId("feature-chart").innerHTML = features.map(([name, count]) => `<div><span>${escapeText(name.replaceAll("-", " "))}</span><i><b style="width:${count / max * 100}%"></b></i><strong>${count}</strong></div>`).join("") || "<p>No activity yet.</p>";
  const purposes = {};
  data.users.forEach((user) => { const key = user.purpose || "Not provided"; purposes[key] = (purposes[key] || 0) + 1; });
  byId("purpose-chart").innerHTML = Object.entries(purposes).sort((a,b) => b[1] - a[1]).map(([name, count]) => `<div><i></i><span>${escapeText(name)}</span><strong>${count}</strong></div>`).join("") || "<p>No profiles yet.</p>";
  customerData = data.users;
  renderCustomers(customerData);
  byId("event-table").innerHTML = data.recent_events.map((event) => `<tr><td><b>${escapeText(event.feature)}</b></td><td class="mono">${escapeText((event.uid || "").slice(0, 12))}…</td><td>${event.anonymous ? "Guest" : "Member"}</td><td>${event.duration_ms || 0} ms</td><td><span class="status ${event.status >= 400 ? "bad" : ""}">${event.status}</span></td><td>${dateText(event.created_at)}</td></tr>`).join("") || `<tr><td colspan="6">No events yet.</td></tr>`;
}
async function loadDashboard() {
  if (auth.currentUser.email?.toLowerCase() !== "chakrabartiaditya10@gmail.com") {
    throw new Error("This Google account is not authorized as a Rosetta administrator.");
  }
  const [userSnapshots, eventSnapshots] = await Promise.all([
    getDocs(query(collection(db, "users"), limit(500))),
    getDocs(query(collection(db, "usage_events"), orderBy("created_at", "desc"), limit(1000)))
  ]);
  const users = userSnapshots.docs.map((snapshot) => snapshot.data());
  const events = eventSnapshots.docs.map((snapshot) => snapshot.data());
  const featureCounts = {};
  let errors = 0;
  let totalSpeed = 0;
  events.forEach((event) => {
    featureCounts[event.feature] = (featureCounts[event.feature] || 0) + 1;
    totalSpeed += Number(event.duration_ms || 0);
    if (event.status >= 400) errors += 1;
  });
  const data = {
    users,
    recent_events: events.slice(0, 100),
    metrics: {
      total_users: users.length,
      registered_users: users.filter((user) => !user.anonymous).length,
      guest_users: users.filter((user) => user.anonymous).length,
      requests: events.length,
      errors,
      average_speed_ms: events.length ? Math.round(totalSpeed / events.length) : 0,
      feature_counts: featureCounts
    }
  };
  byId("admin-auth").classList.add("hidden");
  byId("admin-content").classList.remove("hidden");
  render(data);
}

byId("admin-google").addEventListener("click", () => signInWithPopup(auth, new GoogleAuthProvider()).catch((error) => showError(error.message)));
byId("admin-refresh").addEventListener("click", () => loadDashboard().catch((error) => showError(error.message)));
byId("customer-search").addEventListener("input", (event) => {
  const query = event.target.value.toLowerCase();
  renderCustomers(customerData.filter((user) => JSON.stringify(user).toLowerCase().includes(query)));
});
document.querySelectorAll("[data-scroll]").forEach((button) => button.addEventListener("click", () => byId(button.dataset.scroll).scrollIntoView({ behavior: "smooth" })));

if (configured) {
  const firebaseApp = initializeApp(config);
  auth = getAuth(firebaseApp);
  db = getFirestore(firebaseApp, "default");
  onAuthStateChanged(auth, (user) => {
    if (user) loadDashboard().catch((error) => showError(error.message));
  });
} else {
  byId("admin-google").disabled = true;
  showError("Firebase environment variables are not configured yet.");
}
