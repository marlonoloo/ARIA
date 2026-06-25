/**
 * ARIA Authentication (Amazon Cognito)
 * 
 * Uses Cognito's InitiateAuth and SignUp APIs directly via fetch.
 * No SDK dependency needed — just standard Cognito REST calls.
 * 
 * Flow:
 * 1. Doctor signs in with email/password
 * 2. Cognito returns ID token + access token + refresh token
 * 3. ID token stored in sessionStorage
 * 4. Token sent as Authorization header on protected API calls
 * 5. doctor.html checks for token on load — redirects to login if missing
 */

// === COGNITO CONFIG (from Faith) ===
const COGNITO_REGION = 'us-east-1';
const COGNITO_POOL_ID = 'us-east-1_7EcteStu9';
const COGNITO_CLIENT_ID = '2naufa434t15vjrrl7aru34fqr';
const COGNITO_ENDPOINT = `https://cognito-idp.${COGNITO_REGION}.amazonaws.com`;

// Store email for confirmation flow
let pendingEmail = '';

// === SIGN IN ===

async function handleLogin(event) {
    event.preventDefault();
    
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    const btn = document.getElementById('loginBtn');
    
    hideError('errorMsg');
    btn.textContent = 'Signing in...';
    btn.disabled = true;

    try {
        const response = await fetch(COGNITO_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-amz-json-1.1',
                'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth'
            },
            body: JSON.stringify({
                AuthFlow: 'USER_PASSWORD_AUTH',
                ClientId: COGNITO_CLIENT_ID,
                AuthParameters: {
                    USERNAME: email,
                    PASSWORD: password
                }
            })
        });

        const data = await response.json();

        if (data.AuthenticationResult) {
            // Success — store tokens
            const tokens = data.AuthenticationResult;
            sessionStorage.setItem('aria_id_token', tokens.IdToken);
            sessionStorage.setItem('aria_access_token', tokens.AccessToken);
            sessionStorage.setItem('aria_refresh_token', tokens.RefreshToken || '');
            sessionStorage.setItem('aria_user_email', email);

            // Redirect to doctor dashboard
            window.location.href = 'doctor.html';
        } else if (data.__type && data.__type.includes('NotAuthorizedException')) {
            showError('errorMsg', 'errorText', 'Incorrect email or password.');
        } else if (data.__type && data.__type.includes('UserNotConfirmedException')) {
            showError('errorMsg', 'errorText', 'Please verify your email first.');
            pendingEmail = email;
            showConfirm();
        } else if (data.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
            showError('errorMsg', 'errorText', 'Password reset required. Contact admin.');
        } else {
            showError('errorMsg', 'errorText', data.message || 'Login failed. Please try again.');
        }
    } catch (err) {
        console.error('Login error:', err);
        showError('errorMsg', 'errorText', 'Connection error. Please try again.');
    }

    btn.textContent = 'Sign In';
    btn.disabled = false;
}

// === SIGN UP ===

async function handleSignUp(event) {
    event.preventDefault();

    const name = document.getElementById('signUpName').value.trim();
    const email = document.getElementById('signUpEmail').value.trim();
    const password = document.getElementById('signUpPassword').value;
    const btn = document.getElementById('signUpBtn');

    hideError('signUpErrorMsg');
    btn.textContent = 'Creating account...';
    btn.disabled = true;

    try {
        const response = await fetch(COGNITO_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-amz-json-1.1',
                'X-Amz-Target': 'AWSCognitoIdentityProviderService.SignUp'
            },
            body: JSON.stringify({
                ClientId: COGNITO_CLIENT_ID,
                Username: email,
                Password: password,
                UserAttributes: [
                    { Name: 'email', Value: email },
                    { Name: 'name', Value: name }
                ]
            })
        });

        const data = await response.json();

        if (data.UserSub) {
            // Success — need email confirmation
            pendingEmail = email;
            showConfirm();
        } else if (data.__type && data.__type.includes('UsernameExistsException')) {
            showError('signUpErrorMsg', 'signUpErrorText', 'An account with this email already exists.');
        } else if (data.__type && data.__type.includes('InvalidPasswordException')) {
            showError('signUpErrorMsg', 'signUpErrorText', 'Password must be at least 8 characters with uppercase, lowercase, and numbers.');
        } else {
            showError('signUpErrorMsg', 'signUpErrorText', data.message || 'Sign up failed.');
        }
    } catch (err) {
        console.error('Sign up error:', err);
        showError('signUpErrorMsg', 'signUpErrorText', 'Connection error. Please try again.');
    }

    btn.textContent = 'Create Account';
    btn.disabled = false;
}

// === CONFIRM SIGN UP ===

async function handleConfirm(event) {
    event.preventDefault();

    const code = document.getElementById('confirmCode').value.trim();

    try {
        const response = await fetch(COGNITO_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-amz-json-1.1',
                'X-Amz-Target': 'AWSCognitoIdentityProviderService.ConfirmSignUp'
            },
            body: JSON.stringify({
                ClientId: COGNITO_CLIENT_ID,
                Username: pendingEmail,
                ConfirmationCode: code
            })
        });

        const data = await response.json();

        if (!data.__type) {
            // Success — redirect to login
            alert('Email verified! You can now sign in.');
            showLogin();
            document.getElementById('email').value = pendingEmail;
        } else {
            alert(data.message || 'Invalid code. Please try again.');
        }
    } catch (err) {
        console.error('Confirmation error:', err);
        alert('Connection error. Please try again.');
    }
}

// === UI HELPERS ===

function showLogin() {
    document.getElementById('loginForm').classList.remove('hidden');
    document.getElementById('signUpForm').classList.add('hidden');
    document.getElementById('confirmForm').classList.add('hidden');
}

function showSignUp() {
    document.getElementById('loginForm').classList.add('hidden');
    document.getElementById('signUpForm').classList.remove('hidden');
    document.getElementById('confirmForm').classList.add('hidden');
}

function showConfirm() {
    document.getElementById('loginForm').classList.add('hidden');
    document.getElementById('signUpForm').classList.add('hidden');
    document.getElementById('confirmForm').classList.remove('hidden');
}

function showError(containerId, textId, message) {
    document.getElementById(containerId).classList.remove('hidden');
    document.getElementById(textId).textContent = message;
}

function hideError(containerId) {
    document.getElementById(containerId).classList.add('hidden');
}

// === AUTH UTILITIES (used by other pages) ===

/**
 * Get the stored ID token. Returns null if not logged in.
 */
function getToken() {
    return sessionStorage.getItem('aria_id_token');
}

/**
 * Check if user is authenticated. Redirect to login if not.
 * Call this at the top of protected pages (e.g. doctor.html).
 */
function requireAuth() {
    const token = getToken();
    if (!token) {
        window.location.href = 'doctor-login.html';
        return false;
    }
    return true;
}

/**
 * Log out — clear tokens and redirect to login.
 */
function logout() {
    sessionStorage.removeItem('aria_id_token');
    sessionStorage.removeItem('aria_access_token');
    sessionStorage.removeItem('aria_refresh_token');
    sessionStorage.removeItem('aria_user_email');
    window.location.href = 'doctor-login.html';
}

/**
 * Get auth headers for API calls.
 * Use this in fetch requests to protected endpoints.
 */
function getAuthHeaders() {
    const token = getToken();
    return token ? { 'Authorization': `Bearer ${token}` } : {};
}
