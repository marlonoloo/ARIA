/**
 * ARIA clinic locator — browser geolocation + nearest-clinic lookup.
 *
 * Drop-in for the (anonymous) emergency page. The /nearest-clinic endpoint is
 * public, so NO auth token is required.
 *
 * Usage:
 *   const clinic = await findNearestClinic();             // nearest of any service
 *   const clinic = await findNearestClinic('maternity');  // nearest with a service
 *   // clinic -> { clinic_id, name, location, distance_km }  or  null (none found)
 *
 * Both calls reject if the user denies/!supports geolocation — handle that to
 * fall back (e.g. ask the patient to type their area).
 *
 * NOTE: the page must be served over https or http://localhost for the browser
 * to grant geolocation, and the page's origin must be in the API's CORS allow-list.
 */

const NEAREST_CLINIC_URL = 'https://ju4c4od7u1.execute-api.us-east-1.amazonaws.com/nearest-clinic';

// Resolve the browser's current coordinates as { lat, lng }.
function getBrowserLocation(timeoutMs = 8000) {
    return new Promise((resolve, reject) => {
        if (!('geolocation' in navigator)) {
            reject(new Error('Geolocation is not supported on this device.'));
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
            (err) => reject(err),
            { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60000 }
        );
    });
}

// Look up the nearest clinic for given coordinates. Returns the clinic or null.
async function getNearestClinic(lat, lng, service) {
    const body = { lat, lng };
    if (service) body.service = service;
    const res = await fetch(NEAREST_CLINIC_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (res.status === 404) return null;            // no active clinics matched
    if (!res.ok) throw new Error('Clinic lookup failed (' + res.status + ').');
    const data = await res.json();
    return data.clinic || null;
}

// Convenience: capture location, then find the nearest clinic. Returns clinic or null.
async function findNearestClinic(service) {
    const { lat, lng } = await getBrowserLocation();
    return getNearestClinic(lat, lng, service);
}

/* Example wiring for the emergency page:

    try {
        const clinic = await findNearestClinic();   // or findNearestClinic('maternity')
        if (clinic) {
            showMessage(`Nearest clinic: ${clinic.name} in ${clinic.location}, `
                        + `about ${clinic.distance_km} km away.`);
        } else {
            showMessage('No clinics found nearby. Please call emergency services.');
        }
    } catch (err) {
        // user denied location or it timed out
        showMessage('Please share your location, or tell us your nearest town.');
    }
*/
