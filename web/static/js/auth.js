import { initializeApp } from "https://www.gstatic.com/firebasejs/12.16.0/firebase-app.js";
import {
  browserLocalPersistence,
  browserSessionPersistence,
  createUserWithEmailAndPassword,
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  sendPasswordResetEmail,
  setPersistence,
  signInAnonymously,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut
} from "https://www.gstatic.com/firebasejs/12.16.0/firebase-auth.js";
import {
  addDoc,
  collection,
  doc,
  getDoc,
  getFirestore,
  serverTimestamp,
  setDoc
} from "https://www.gstatic.com/firebasejs/12.16.0/firebase-firestore.js";

const byId = (id) => document.getElementById(id);
const gate = byId("auth-gate");
const form = byId("auth-form");
const email = byId("auth-email");
const password = byId("auth-password");
const submit = byId("auth-submit");
const error = byId("auth-error");
const googleButton = byId("auth-google");
const guestButton = byId("auth-guest");
const setupNote = byId("auth-setup-note");
const userMenu = byId("auth-user-menu");
const userAvatar = byId("auth-user-avatar");
const userName = byId("auth-user-name");
const signoutButton = byId("auth-signout");
const sourceText = byId("source-text");
const onboardingGate = byId("onboarding-gate");
const onboardingForm = byId("onboarding-form");
const adminLink = byId("admin-dashboard-link");
const config = JSON.parse(byId("firebase-config-data").textContent);
const configured = Boolean(config.apiKey && config.authDomain && config.projectId && config.appId);
const restrictedForGuests = new Set([
  "btn-writing", "btn-camera", "btn-tool-voice", "btn-companion",
  "iris-fab", "btn-practice", "btn-captions", "btn-upgrade"
]);
let signupMode = false;
let auth = null;
let db = null;
// No admin identity lives in this file any more. The dashboard has its own
// passphrase (see web/admin_auth.py); publishing the administrator's email
// here told an attacker exactly which account to go after, and the check it
// fed was client-side anyway, so anyone could flip it in devtools.
const nativeFetch = window.fetch.bind(window);

gate.addEventListener("pointermove", (event) => {
  gate.style.setProperty("--auth-pointer-x", `${event.clientX}px`);
  gate.style.setProperty("--auth-pointer-y", `${event.clientY}px`);
});
document.querySelectorAll(".auth-google, .auth-submit, .auth-guest").forEach((button) => {
  button.addEventListener("pointerdown", (event) => {
    const ripple = document.createElement("i");
    const bounds = button.getBoundingClientRect();
    ripple.className = "auth-ripple";
    ripple.style.left = `${event.clientX - bounds.left}px`;
    ripple.style.top = `${event.clientY - bounds.top}px`;
    button.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove());
  });
});

window.fetch = async (input, init = {}) => {
  const url = typeof input === "string" ? input : input.url;
  if (!url.startsWith("/api/") || !auth?.currentUser) return nativeFetch(input, init);
  const started = performance.now();
  const headers = new Headers(init.headers || (typeof input !== "string" ? input.headers : undefined));
  headers.set("Authorization", `Bearer ${await auth.currentUser.getIdToken()}`);
  const response = await nativeFetch(input, { ...init, headers });
  if (!["/api/config", "/api/profile", "/api/admin/analytics"].includes(url.split("?")[0]) && db) {
    addDoc(collection(db, "usage_events"), {
      uid: auth.currentUser.uid,
      feature: url.split("?")[0].replace("/api/", ""),
      method: init.method || "GET",
      status: response.status,
      duration_ms: Math.round((performance.now() - started) * 10) / 10,
      anonymous: auth.currentUser.isAnonymous,
      created_at: serverTimestamp()
    }).catch(() => {});
  }
  return response;
};

function messageFor(errorObject) {
  const code = errorObject?.code || "";
  if (code.includes("invalid-credential")) return "The email or password is incorrect.";
  if (code.includes("email-already-in-use")) return "An account already exists for this email.";
  if (code.includes("weak-password")) return "Choose a stronger password with at least 6 characters.";
  if (code.includes("popup-closed")) return "Google sign-in was closed before it finished.";
  if (code.includes("popup-blocked")) return "Allow popups for Rosetta, then try Google sign-in again.";
  if (code.includes("unauthorized-domain")) return "Add this domain to Firebase Authentication → Authorized domains.";
  if (code.includes("network-request-failed")) return "Check your connection and try again.";
  if (code.includes("operation-not-allowed")) return "Google sign-in is not enabled for this Firebase project.";
  if (code.includes("internal-error")) return "Firebase could not complete Google sign-in. Please try once more.";
  // Strips the trailing " (auth/invalid-credential)." Firebase appends.
  // The backslashes here must be single: `\\(` matches a literal backslash and
  // then opens a group that is never closed, which is an early SyntaxError --
  // and because it is thrown at parse time, the entire module fails to
  // evaluate and not one listener in this file gets attached.
  const message = errorObject?.message
    ?.replace(/^Firebase: /, "")
    .replace(/\s*\(auth\/[^)]+\)\.?$/, "");
  if (message && message !== "Error") return message;
  return code
    ? `Google sign-in failed (${code}).`
    : "Google sign-in could not start. Check that popups are allowed, then try again.";
}

function showError(text, good = false) {
  error.textContent = text;
  error.classList.remove("hidden", "is-good");
  if (good) error.classList.add("is-good");
}

function setBusy(busy, label = "Please wait…") {
  submit.disabled = busy;
  googleButton.disabled = busy;
  if (busy) submit.querySelector("span").textContent = label;
  else submit.querySelector("span").textContent = signupMode ? "Create account" : "Sign in";
}

async function loadProfile(user) {
  const snapshot = await getDoc(doc(db, "users", user.uid));
  return {
    profile: snapshot.exists() ? snapshot.data() : null,
    is_admin: false,  // decided by the server, behind a separate passphrase
    anonymous: user.isAnonymous
  };
}

function revealApp(profile, isAdmin = false) {
  document.body.classList.remove("auth-pending");
  gate.classList.add("is-leaving");
  setTimeout(() => gate.classList.add("hidden"), 430);
  userMenu.classList.remove("hidden");
  signoutButton.classList.remove("hidden");
  userName.textContent = profile.name;
  userAvatar.textContent = profile.name.slice(0, 1).toUpperCase();
  userMenu.classList.toggle("is-guest", profile.guest);
  userMenu.title = profile.guest ? "Guest mode · limited access" : profile.email || "Signed in";
  document.body.dataset.access = profile.guest ? "guest" : "member";
  adminLink?.classList.toggle("hidden", !isAdmin);
  window.dispatchEvent(new CustomEvent("rosetta:auth-ready", { detail: profile }));
}

function revealAuthenticatedUser(user) {
  const fallbackName = (user.displayName || "").trim()
    || (user.email || "").split("@")[0]
    || "Member";
  revealApp({
    name: fallbackName,
    email: user.email || "",
    guest: user.isAnonymous
  });
}

function openOnboarding(user) {
  gate.classList.add("hidden");
  onboardingGate.classList.remove("hidden");
  document.body.classList.add("auth-pending");
  const displayParts = (user.displayName || "").trim().split(/\s+/);
  byId("onboarding-first-name").value = displayParts[0] || "";
  byId("onboarding-last-name").value = displayParts.slice(1).join(" ");
}

function showGate() {
  sessionStorage.removeItem("rosetta-guest");
  document.body.classList.add("auth-pending");
  document.body.dataset.access = "";
  gate.classList.remove("hidden", "is-leaving");
  userMenu.classList.add("hidden");
  signoutButton.classList.add("hidden");
  adminLink?.classList.add("hidden");
}

async function leaveGuestAndShowGate() {
  // Anonymous Firebase users are still authenticated users. Starting Google
  // redirect auth on top of that guest session can return to guest mode or
  // fail with an account-linking error. Guest mode stores no irreplaceable
  // account data, so end it before presenting the real sign-in choices.
  if (auth?.currentUser?.isAnonymous) {
    try {
      await signOut(auth);
    } catch {
      // The sign-in screen is still the useful recovery path if the guest
      // token has already expired or cannot be revoked locally.
    }
  }
  showGate();
}

function guestNotice() {
  let toast = byId("guest-limit-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "guest-limit-toast";
    toast.className = "guest-limit-toast";
    toast.innerHTML = "<b>Member feature</b><span>Sign in free to unlock voice, camera, captions, Iris and writing tools.</span><button type=\"button\">Sign in</button>";
    document.body.appendChild(toast);
    toast.querySelector("button").addEventListener("click", leaveGuestAndShowGate);
  }
  toast.classList.add("is-visible");
  clearTimeout(guestNotice.timer);
  guestNotice.timer = setTimeout(() => toast.classList.remove("is-visible"), 4500);
}

document.addEventListener("click", (event) => {
  if (document.body.dataset.access !== "guest") return;
  const restricted = event.target.closest("[id]");
  if (!restricted || !restrictedForGuests.has(restricted.id)) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  guestNotice();
}, true);

sourceText?.addEventListener("input", () => {
  if (document.body.dataset.access !== "guest" || sourceText.value.length <= 250) return;
  sourceText.value = sourceText.value.slice(0, 250);
  sourceText.dispatchEvent(new Event("input", { bubbles: false }));
  guestNotice();
});

guestButton.addEventListener("click", () => {
  if (!auth) return showError("Connect Firebase and enable Anonymous Authentication to use guest mode.");
  setBusy(true, "Creating guest session…");
  signInAnonymously(auth).catch((authError) => {
    showError(messageFor(authError));
    setBusy(false);
  });
});

byId("onboarding-next").addEventListener("click", () => {
  if (!byId("onboarding-first-name").value.trim() || !byId("onboarding-last-name").value.trim()) {
    byId("onboarding-step-one").querySelector("input:invalid")?.reportValidity();
    return;
  }
  byId("onboarding-step-one").classList.add("hidden");
  byId("onboarding-step-two").classList.remove("hidden");
  document.querySelectorAll(".onboarding-progress i")[1].classList.add("is-active");
});
byId("onboarding-back").addEventListener("click", () => {
  byId("onboarding-step-two").classList.add("hidden");
  byId("onboarding-step-one").classList.remove("hidden");
  document.querySelectorAll(".onboarding-progress i")[1].classList.remove("is-active");
});
onboardingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const onboardingError = byId("onboarding-error");
  const submitButton = byId("onboarding-submit");
  submitButton.disabled = true;
  onboardingError.classList.add("hidden");
  try {
    const profile = {
      uid: auth.currentUser.uid,
      email: auth.currentUser.email || null,
      anonymous: auth.currentUser.isAnonymous,
      first_name: byId("onboarding-first-name").value.trim(),
      last_name: byId("onboarding-last-name").value.trim(),
      role: byId("onboarding-role").value,
      purpose: byId("onboarding-purpose").value,
      last_seen_at: serverTimestamp()
    };
    const profileRef = doc(db, "users", auth.currentUser.uid);
    const existing = await getDoc(profileRef);
    await setDoc(profileRef, {
      ...profile,
      ...(existing.exists() ? {} : { created_at: serverTimestamp() })
    }, { merge: true });
    onboardingGate.classList.add("hidden");
    revealApp({
      name: `${byId("onboarding-first-name").value.trim()} ${byId("onboarding-last-name").value.trim()}`,
      email: auth.currentUser.email || "",
      guest: auth.currentUser.isAnonymous
    }, false);
  } catch (saveError) {
    onboardingError.textContent = saveError.message;
    onboardingError.classList.remove("hidden");
  } finally {
    submitButton.disabled = false;
  }
});

byId("auth-show-password").addEventListener("click", (event) => {
  const revealing = password.type === "password";
  password.type = revealing ? "text" : "password";
  event.currentTarget.textContent = revealing ? "Hide" : "Show";
});

byId("auth-switch-mode").addEventListener("click", () => {
  signupMode = !signupMode;
  byId("auth-form-title").textContent = signupMode ? "Create your account" : "Sign in to continue";
  byId("auth-form-subtitle").textContent = signupMode ? "Start your private language workspace in seconds." : "Unlock your complete language workspace.";
  byId("auth-switch-copy").textContent = signupMode ? "Already have an account?" : "New to Rosetta?";
  byId("auth-switch-mode").textContent = signupMode ? "Sign in instead" : "Create an account";
  submit.querySelector("span").textContent = signupMode ? "Create account" : "Sign in";
  password.autocomplete = signupMode ? "new-password" : "current-password";
  error.classList.add("hidden");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!auth) return showError("Firebase is not connected yet. Use guest preview for now.");
  setBusy(true, signupMode ? "Creating account…" : "Signing in…");
  error.classList.add("hidden");
  try {
    sessionStorage.setItem("rosetta-upgrade-after-login", "1");
    await setPersistence(auth, byId("auth-remember").checked ? browserLocalPersistence : browserSessionPersistence);
    if (signupMode) await createUserWithEmailAndPassword(auth, email.value.trim(), password.value);
    else await signInWithEmailAndPassword(auth, email.value.trim(), password.value);
  } catch (authError) {
    sessionStorage.removeItem("rosetta-upgrade-after-login");
    showError(messageFor(authError));
    setBusy(false);
  }
});

googleButton.addEventListener("click", () => {
  if (!auth) return showError("Firebase is not connected yet. Use guest preview for now.");
  // A popup must be opened synchronously from this click. Any `await` before
  // signInWithPopup consumes the browser's transient user activation and the
  // popup is then blocked (some Firebase/browser combinations report only
  // the unhelpful message "Error").
  if (auth.currentUser?.isAnonymous) {
    setBusy(true, "Closing guest session…");
    signOut(auth).then(() => {
      setBusy(false);
      showError("Guest session closed. Click Continue with Google once more.", true);
    }).catch((authError) => {
      showError(messageFor(authError));
      setBusy(false);
    });
    return;
  }
  setBusy(true, "Opening Google…");
  error.classList.add("hidden");
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  sessionStorage.setItem("rosetta-upgrade-after-login", "1");
  signInWithPopup(auth, provider).catch((authError) => {
    sessionStorage.removeItem("rosetta-upgrade-after-login");
    showError(messageFor(authError));
    setBusy(false);
  });
});

byId("auth-forgot").addEventListener("click", async () => {
  if (!auth) return showError("Firebase is not connected yet.");
  if (!email.value.trim()) {
    showError("Enter your email address first, then choose Forgot password.");
    email.focus();
    return;
  }
  try {
    await sendPasswordResetEmail(auth, email.value.trim());
    showError("Password reset email sent. Check your inbox.", true);
  } catch (authError) {
    showError(messageFor(authError));
  }
});

signoutButton.addEventListener("click", async () => {
  if (auth?.currentUser) await signOut(auth);
  showGate();
});
userMenu.addEventListener("click", () => {
  if (document.body.dataset.access === "guest") leaveGuestAndShowGate();
});

if (configured) {
  const firebaseApp = initializeApp(config);
  auth = getAuth(firebaseApp);
  // Configure persistence outside the Google button's click handler so it
  // cannot delay popup creation. Firebase defaults to local persistence; this
  // keeps the checkbox preference in sync before the next authentication.
  const rememberControl = byId("auth-remember");
  rememberControl.addEventListener("change", () => {
    setPersistence(
      auth,
      rememberControl.checked ? browserLocalPersistence : browserSessionPersistence
    ).catch((persistenceError) => showError(messageFor(persistenceError)));
  });
  // Production may use a named Firestore database. Keep the browser on the
  // same database as the Flask/Firebase Admin backend; omit the argument only
  // when no custom id is configured, which selects Firebase's `(default)`.
  db = config.databaseId
    ? getFirestore(firebaseApp, config.databaseId)
    : getFirestore(firebaseApp);
  onAuthStateChanged(auth, (user) => {
    setBusy(false);
    if (user) {
      loadProfile(user).then((data) => {
        if (!data.profile) {
          openOnboarding(user);
          return;
        }
        revealApp({
          name: `${data.profile.first_name || ""} ${data.profile.last_name || ""}`.trim() || "Member",
          email: user.email || "",
          guest: user.isAnonymous
        }, data.is_admin);
      }).catch((profileError) => {
        // Authentication and optional profile storage are separate concerns.
        // A valid Google user must not be thrown back to sign-in just because
        // Firestore is unavailable or its rules are being deployed.
        console.warn("Profile storage unavailable; continuing with Firebase Auth.", profileError);
        revealAuthenticatedUser(user);
      });
    } else {
      document.body.classList.remove("auth-pending");
    }
  });
} else {
  googleButton.disabled = true;
  submit.disabled = true;
  setupNote.classList.remove("hidden");
  document.body.classList.remove("auth-pending");
}
