// Cognito Authentication Module
// Uses amazon-cognito-identity-js for authentication

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserAttribute
} from 'amazon-cognito-identity-js';

// Get configuration from environment variables
const USER_POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID;
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID;

if (!USER_POOL_ID || !CLIENT_ID) {
  console.warn('⚠️ Cognito configuration missing. Set VITE_COGNITO_USER_POOL_ID and VITE_COGNITO_CLIENT_ID');
}

const poolData = {
  UserPoolId: USER_POOL_ID,
  ClientId: CLIENT_ID
};

export const userPool = USER_POOL_ID && CLIENT_ID ? new CognitoUserPool(poolData) : null;

/**
 * Sign in a user with username and password
 * @param {string} username - Username (email)
 * @param {string} password - Password
 * @returns {Promise<string>} JWT token
 */
export async function signIn(username, password) {
  if (!userPool) {
    throw new Error('Cognito not configured');
  }

  return new Promise((resolve, reject) => {
    const authenticationDetails = new AuthenticationDetails({
      Username: username,
      Password: password
    });

    const cognitoUser = new CognitoUser({
      Username: username,
      Pool: userPool
    });

    cognitoUser.authenticateUser(authenticationDetails, {
      onSuccess: (result) => {
        const token = result.getIdToken().getJwtToken();
        // Store token in localStorage
        localStorage.setItem('cognito_token', token);
        localStorage.setItem('cognito_username', username);
        resolve(token);
      },
      onFailure: (err) => {
        console.error('Authentication failed:', err);
        reject(err);
      },
      newPasswordRequired: (userAttributes, requiredAttributes) => {
        // Handle new password required (first-time login)
        reject(new Error('New password required. Please contact administrator.'));
      }
    });
  });
}

/**
 * Sign out the current user
 */
export function signOut() {
  const cognitoUser = getCurrentUser();
  if (cognitoUser) {
    cognitoUser.signOut();
    localStorage.removeItem('cognito_token');
    localStorage.removeItem('cognito_username');
  }
}

/**
 * Get the current authenticated user
 * @returns {CognitoUser|null}
 */
export function getCurrentUser() {
  if (!userPool) {
    return null;
  }
  return userPool.getCurrentUser();
}

/**
 * Get the current session
 * @returns {Promise<CognitoUserSession>}
 */
export function getSession() {
  return new Promise((resolve, reject) => {
    if (!userPool) {
      reject(new Error('Cognito not configured'));
      return;
    }

    const cognitoUser = getCurrentUser();
    if (!cognitoUser) {
      reject(new Error('No user'));
      return;
    }

    cognitoUser.getSession((err, session) => {
      if (err) {
        reject(err);
      } else if (!session.isValid()) {
        reject(new Error('Session expired'));
      } else {
        resolve(session);
      }
    });
  });
}

/**
 * Get the current JWT token
 * @returns {Promise<string>}
 */
export async function getAuthToken() {
  try {
    // Try to get from localStorage first (faster)
    const cachedToken = localStorage.getItem('cognito_token');
    if (cachedToken) {
      // Verify token is still valid (basic check - not expired)
      try {
        const session = await getSession();
        return session.getIdToken().getJwtToken();
      } catch (err) {
        // Token expired, remove from cache
        localStorage.removeItem('cognito_token');
        throw new Error('Session expired');
      }
    }

    // Get fresh token from session
    const session = await getSession();
    const token = session.getIdToken().getJwtToken();
    localStorage.setItem('cognito_token', token);
    return token;
  } catch (err) {
    throw err;
  }
}

/**
 * Check if user is authenticated
 * @returns {Promise<boolean>}
 */
export async function isAuthenticated() {
  try {
    await getSession();
    return true;
  } catch (err) {
    return false;
  }
}

/**
 * Register a new user
 * @param {string} email - Email address
 * @param {string} password - Password
 * @returns {Promise<void>}
 */
export async function signUp(email, password) {
  if (!userPool) {
    throw new Error('Cognito not configured');
  }

  return new Promise((resolve, reject) => {
    const attributeList = [
      new CognitoUserAttribute({
        Name: 'email',
        Value: email
      })
    ];

    userPool.signUp(email, password, attributeList, null, (err, result) => {
      if (err) {
        reject(err);
      } else {
        resolve(result);
      }
    });
  });
}

/**
 * Confirm user registration with verification code
 * @param {string} username - Username (email)
 * @param {string} code - Verification code
 * @returns {Promise<void>}
 */
export async function confirmSignUp(username, code) {
  if (!userPool) {
    throw new Error('Cognito not configured');
  }

  return new Promise((resolve, reject) => {
    const cognitoUser = new CognitoUser({
      Username: username,
      Pool: userPool
    });

    cognitoUser.confirmRegistration(code, true, (err, result) => {
      if (err) {
        reject(err);
      } else {
        resolve(result);
      }
    });
  });
}

