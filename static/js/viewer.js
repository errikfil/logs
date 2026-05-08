console.log("viewer.js loaded");

const flightData = window.flightData || [];

if (flightData.length === 0) {
    console.error("No flight data found");
}

const map = L.map("map").setView(
    [flightData[0].latitude, flightData[0].longitude],
    15
);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap"
}).addTo(map);

const coordinates = flightData.map(point => [
    point.latitude,
    point.longitude
]);

const route = L.polyline(coordinates, {
    color: "#ef4444",
    weight: 4,
    opacity: 0.9
}).addTo(map);

map.fitBounds(route.getBounds());

L.circleMarker(coordinates[0], {
    radius: 9,
    color: "#22c55e",
    fillColor: "#22c55e",
    fillOpacity: 1
}).addTo(map).bindPopup("Start");

L.circleMarker(coordinates[coordinates.length - 1], {
    radius: 9,
    color: "#ef4444",
    fillColor: "#ef4444",
    fillOpacity: 1
}).addTo(map).bindPopup("End");

const droneIcon = L.divIcon({
    className: "drone-marker",
    html: "🚁",
    iconSize: [32, 32],
    iconAnchor: [16, 16]
});

const replayMarker = L.marker(coordinates[0], {
    icon: droneIcon
}).addTo(map);

const maxAltitude = Math.max(...flightData.map(p => Number(p.altitude) || 0));
const maxSpeed = Math.max(...flightData.map(p => Number(p.speed) || 0));

document.getElementById("maxAltitude").textContent = `${maxAltitude.toFixed(1)} m`;
document.getElementById("maxSpeed").textContent = `${maxSpeed.toFixed(1)} km/h`;

let replayIndex = 0;
let replayInterval = null;
let replayPlaying = false;

function updatePlayPauseButton() {
    const button = document.getElementById("playPauseBtn");

    if (!button) return;

    button.textContent = replayPlaying ? "⏸ Pause" : "▶ Play";
}

function toggleReplay() {
    if (replayPlaying) {
        pauseReplay();
    } else {
        startReplay();
    }
}

function startReplay() {
    if (replayInterval) return;

    replayPlaying = true;
    updatePlayPauseButton();

    replayInterval = setInterval(() => {
        if (replayIndex >= flightData.length) {
            pauseReplay();
            replayIndex = 0;
            updatePlayPauseButton();
            return;
        }

        const point = flightData[replayIndex];

        replayMarker.setLatLng([
            point.latitude,
            point.longitude
        ]);

        map.panTo([
            point.latitude,
            point.longitude
        ]);

        replayIndex++;

    }, 250);
}

function pauseReplay() {
    replayPlaying = false;

    clearInterval(replayInterval);
    replayInterval = null;

    updatePlayPauseButton();
}

function resetReplay() {
    pauseReplay();

    replayIndex = 0;

    replayMarker.setLatLng(coordinates[0]);
    map.panTo(coordinates[0]);

    updatePlayPauseButton();
}

window.toggleReplay = toggleReplay;
window.startReplay = startReplay;
window.pauseReplay = pauseReplay;
window.resetReplay = resetReplay;

updatePlayPauseButton();

console.log("viewer.js ready");