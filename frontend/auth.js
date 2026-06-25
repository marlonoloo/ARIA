/**
 * ARIA frontend — shared Cognito auth + authenticated API helper.
 *
 * Loaded by both login.html and chat.html (after the amazon-cognito-identity-js
 * SDK, which provides the AmazonCognitoIdentity global). Tokens are persisted in
 * localStorage by the SDK, so a session established on login.html is visible to
 * chat.html on the same origin.
 */

// === CONFIG (point the pages at the deployed Triage API) ===
const ARIA_CONFIG = {
    apiBaseUrl: 'https://ju4c4od7u1.execute-api.us-east-1.amazonaws.com',
    region: 'us-east-1',
    userPoolId: 'us-east-1_7EcteStu9',
    clientId: '2naufa434t15vjrrl7aru34fqr',
};

const userPool = new AmazonCognitoIdentity.CognitoUserPool({
    UserPoolId: ARIA_CONFIG.userPoolId,
    ClientId: ARIA_CONFIG.clientId,
});
let cognitoUser = null;

// Sign in with username/password using the USER_PASSWORD_AUTH flow.
function signIn(username, password) {
    return new Promise((resolve, reject) => {
        const authDetails = new AmazonCognitoIdentity.AuthenticationDetails({
            Username: username, Password: password,
        });
        const user = new AmazonCognitoIdentity.CognitoUser({ Username: username, Pool: userPool });
        user.setAuthenticationFlowType('USER_PASSWORD_AUTH');
        user.authenticateUser(authDetails, {
            onSuccess: (session) => { cognitoUser = user; resolve(session); },
            onFailure: (err) => reject(err),
            newPasswordRequired: () => reject(new Error('This account needs a new password set before sign-in.')),
        });
    });
}

// Resolve a valid ID token, refreshing silently if needed. Rejects when not signed in.
function getIdToken() {
    return new Promise((resolve, reject) => {
        const user = cognitoUser || userPool.getCurrentUser();
        if (!user) { reject(new Error('not-signed-in')); return; }
        user.getSession((err, session) => {
            if (err || !session || !session.isValid()) { reject(new Error('not-signed-in')); return; }
            cognitoUser = user;
            resolve(session.getIdToken().getJwtToken());
        });
    });
}

function signOut() {
    const user = cognitoUser || userPool.getCurrentUser();
    if (user) user.signOut();
    cognitoUser = null;
}

function redirectToLogin() { window.location.href = 'login.html'; }

// Authenticated POST to the Triage API. Redirects to login if the session is gone.
async function authedPost(path, body) {
    let token;
    try {
        token = await getIdToken();
    } catch (e) {
        redirectToLogin();
        throw new Error('not-signed-in');
    }
    const res = await fetch(ARIA_CONFIG.apiBaseUrl + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error('Sorry, that request failed (' + res.status + '). Please try again.');
    return res.json();
}
