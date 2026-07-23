var STATUS_EMOJI = {
  "Available": "\u2705",
  "Doubt": "\u2753",
  "Doubt + Last yellow card": "\u26A0\uFE0F",
  "Injury": "\u274C",
  "Red card": "\uD83D\uDFE5",
  "Yellow red card": "\uD83D\uDFE5",
  "Last Yellow card": "\uD83D\uDFE8",
  "Not playing (Called up)": "\u2708\uFE0F",
  "Not playing (Other)": "\uD83D\uDEAB",
  "Return (Injury)": "\uD83D\uDD19",
  "Return (Susp)": "\uD83D\uDD19",
  "Return (Called up)": "\uD83D\uDD19",
  "Return (Other)": "\uD83D\uDD19",
  "New player": "\uD83C\uDD95",
  "Left the team": "\uD83D\uDEAA"
};

function updateStatusIcon(s) {
  var val = s.value;
  var wrapper = s.parentElement;
  var display = wrapper.querySelector(".status-emoji-display");
  if (display && STATUS_EMOJI[val]) {
    display.textContent = STATUS_EMOJI[val];
  }
  var row = wrapper.closest("tr");
  if (!row) return;
  var player = row.querySelector("td.player-name");
  if (!player) return;
  player.classList.remove("status-red","status-green","status-orange");
  player.style.color = "";
  player.style.fontWeight = "";
  player.style.textDecoration = "";
  var x = ["Injury","Red card","Yellow red card","Not playing (Called up)","Not playing (Other)","Left the team"];
  var g = ["Return (Injury)","Return (Susp)","Return (Called up)","Return (Other)","New player"];
  // Doubt treatments (Jul 23 2026): both ❓ Doubt and ⚠️ Doubt + Last yellow card
  // get the same gray + bold + underline styling on the player name.
  var d = ["Doubt", "Doubt + Last yellow card"];
  if (x.indexOf(val) !== -1) player.classList.add("status-red");
  else if (g.indexOf(val) !== -1) player.classList.add("status-green");
  else if (d.indexOf(val) !== -1) {
    player.style.color = "#5F5D58";
    player.style.fontWeight = "bold";
    player.style.textDecoration = "underline";
  }
}

document.addEventListener("DOMContentLoaded", function() {
  document.querySelectorAll(".status-select").forEach(function(s) {
    var val = s.value;
    var wrapper = s.parentElement;
    var display = wrapper.querySelector(".status-emoji-display");
    if (display && STATUS_EMOJI[val]) {
      display.textContent = STATUS_EMOJI[val];
    }
  });
});
