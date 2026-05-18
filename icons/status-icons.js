var STATUS_EMOJI = {
  "Available": "\u2705",
  "Doubt": "\u2753",
  "Injury": "\u274C",
  "Red card": "\uD83D\uDFE5",
  "Yellow red card": "\uD83D\uDFE5",
  "Last Yellow card": "\uD83D\uDFE8",
  "Not playing (Called up)": "\u2708\uFE0F",
  "Not playing (Other)": "\uD83D\uDEAB",
  "Return (Injury)": "\uD83D\uDD19",
  "Return (Susp)": "\uD83D\uDD19",
  "Return (Called up)": "\uD83D\uDD19",
  "Return (Other)": "\uD83D\uDD19"
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
  var x = ["Injury","Red card","Yellow red card","Not playing (Called up)","Not playing (Other)"];
  var g = ["Return (Injury)","Return (Susp)","Return (Called up)","Return (Other)"];
  var o = ["Doubt"];
  if (x.indexOf(val) !== -1) player.classList.add("status-red");
  else if (g.indexOf(val) !== -1) player.classList.add("status-green");
  else if (o.indexOf(val) !== -1) player.classList.add("status-orange");
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
