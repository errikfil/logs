console.log(window.flightData);
console.log("viewer.js loaded");

var flightData = window.flightData || [];

var flightPath = flightData.map(function(point) {
    return [point.latitude, point.longitude];
});

var maxAltitude = Math.max(...flightData.map(function(p) {
    return p.altitude;
}));

var maxSpeed = Math.max(...flightData.map(function(p) {
    return p.speed;
}));

document.getElementById("maxAltitude").innerText = maxAltitude + " m";
document.getElementById("maxSpeed").innerText = maxSpeed + " km/h";

var map = L.map("map").setView(flightPath[0], 15);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "OpenStreetMap"
}).addTo(map);

var route = L.polyline(flightPath, {
    color: "#ef4444",
    weight: 5
}).addTo(map);

L.circleMarker(flightPath[0], {
    radius: 8,
    color: "#22c55e",
    fillColor: "#22c55e",
    fillOpacity: 1
}).addTo(map).bindPopup("Start");

L.circleMarker(flightPath[flightPath.length - 1], {
    radius: 8,
    color: "#ef4444",
    fillColor: "#ef4444",
    fillOpacity: 1
}).addTo(map).bindPopup("End");

var droneMarker = L.circleMarker(flightPath[0], {
    radius: 10,
    color: "#38bdf8",
    fillColor: "#38bdf8",
    fillOpacity: 1
}).addTo(map).bindPopup("Drone");

map.fitBounds(route.getBounds());

window.startReplay = function() {
    var currentIndex = 0;

    var replayInterval = setInterval(function() {
        if (currentIndex >= flightPath.length) {
            clearInterval(replayInterval);
            return;
        }

        droneMarker.setLatLng(flightPath[currentIndex]);
        currentIndex++;
    }, 700);
};