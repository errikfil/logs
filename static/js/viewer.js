console.log("viewer.js loaded");

const flightData = window.flightData || [];

if (!flightData.length) {
    console.error("No flight data found");
}

const map = L.map("map").setView(
    [flightData[0].latitude, flightData[0].longitude],
    16
);

L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
        attribution: "Tiles © Esri"
    }
).addTo(map);

const coordinates = flightData.map(point => [
    Number(point.latitude),
    Number(point.longitude)
]);

const route = L.polyline(coordinates, {
    color: "#ef4444",
    weight: 4,
    opacity: 0.9
}).addTo(map);

map.fitBounds(route.getBounds());

const droneIcon = L.divIcon({
    className: "drone-marker",
    html: '<div style="font-size:42px;">🚁</div>',
    iconSize: [42, 42],
    iconAnchor: [21, 21]
});

const replayMarker = L.marker(coordinates[0], {
    icon: droneIcon
}).addTo(map);

let replayIndex = 0;
let replayInterval = null;
let replayPlaying = false;

const replaySlider = document.getElementById("replaySlider");
const replayCurrent = document.getElementById("replayCurrent");
const playPauseBtn = document.getElementById("playPauseBtn");
const leftStick = document.getElementById("phantomLeftStick");
const rightStick = document.getElementById("phantomRightStick");

function updateReplayPosition(index) {
    replayIndex = Number(index);

    highlightActiveRow(replayIndex);

    const point = flightData[replayIndex];

    const leftStick = document.getElementById("phantomLeftStick");
    const rightStick = document.getElementById("phantomRightStick");

    const yaw = Number(point.rc_yaw || 0);
    const throttle = Number(point.rc_throttle || 0);
    const roll = Number(point.rc_roll || 0);
    const pitch = Number(point.rc_pitch || 0);

    leftStick.style.transform =
        `translate(${yaw / 25}px, ${-throttle / 25}px)`;

    rightStick.style.transform =
        `translate(${roll / 25}px, ${-pitch / 25}px)`;

    replayMarker.setLatLng([
        Number(point.latitude),
        Number(point.longitude)
    ]);

    if (replaySlider) {
        replaySlider.value = replayIndex;
    }

    if (replayCurrent) {
        replayCurrent.textContent = replayIndex;
    }

    document.getElementById("liveAltitude").textContent =
        `${Number(point.altitude || point.imu_altitude || 0).toFixed(1)} m`;

    document.getElementById("liveSpeed").textContent =
        `${Number(point.speed || 0).toFixed(1)} km/h`;

    document.getElementById("liveBattery").textContent =
        `${Number(point.battery || 0).toFixed(0)}%`;

    document.getElementById("liveCoords").textContent =
        `${Number(point.latitude).toFixed(5)}, ${Number(point.longitude).toFixed(5)}`;
}

function updatePlayPauseButton() {
    if (!playPauseBtn) return;

    playPauseBtn.textContent = replayPlaying ? "⏸ Pause" : "▶ Play";
}

function startReplay() {
    console.log("Replay started");

    if (replayInterval) return;

    replayPlaying = true;
    updatePlayPauseButton();

    replayInterval = setInterval(() => {
        console.log("index:", replayIndex);

        if (replayIndex >= flightData.length - 1) {
            pauseReplay();
            return;
        }

        updateReplayPosition(replayIndex + 1);
    }, 120);
}

function pauseReplay() {
    replayPlaying = false;

    clearInterval(replayInterval);
    replayInterval = null;

    updatePlayPauseButton();
}

function toggleReplay() {
    if (replayPlaying) {
        pauseReplay();
    } else {
        startReplay();
    }
}

function resetReplay() {
    pauseReplay();
    updateReplayPosition(0);
}


function highlightActiveRow(index) {

    // remove old
    document.querySelectorAll(".log-row").forEach(row => {
        row.classList.remove("active-log-row");
    });

    // find current row
    const activeRow = document.querySelector(
        `.log-row[data-index="${index}"]`
    );

    console.log("ACTIVE ROW:", activeRow);

    if (activeRow) {

        // add class
        activeRow.classList.add("active-log-row");

        // scroll table
        const tableContainer = document.querySelector(".table-wrap");

        tableContainer.scrollTo({
            top: activeRow.offsetTop - 120,
            behavior: "smooth"
});
    }
}
document.addEventListener("DOMContentLoaded", function () {
    const playBtn = document.getElementById("playPauseBtn");
    const resetBtn = document.getElementById("resetBtn");
    const slider = document.getElementById("replaySlider");

    if (playBtn) {
        playBtn.addEventListener("click", toggleReplay);
    }

    if (resetBtn) {
        resetBtn.addEventListener("click", resetReplay);
    }

    if (slider) {
        slider.addEventListener("input", function () {
            pauseReplay();
            updateReplayPosition(Number(this.value));
        });
    }

    updateReplayPosition(0);
});
function enableTableRowClick() {
    document.querySelectorAll(".log-row").forEach(row => {
        row.addEventListener("click", function () {
            const index = Number(this.dataset.index);

            pauseReplay();
            updateReplayPosition(index);
        });
    });
}

window.toggleReplay = toggleReplay;
window.resetReplay = resetReplay;

updateReplayPosition(0);
updatePlayPauseButton();
enableTableRowClick();

console.log("viewer.js ready");