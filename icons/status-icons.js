const STATUS_EMOJI = {
  'Available': '✅',
  'Doubt': '❓',
  'Injury': '❌',
  'Red card': '🟥',
  'Yellow red card': '🟥',
  'Last Yellow card': '🟨',
  'Not playing (Called up)': '✈️',
  'Not playing (Other)': '🚫',
  'Return (Injury)': '🔙',
  'Return (Susp)': '🔙',
  'Return (Called up)': '🔙',
  'Return (Other)': '🔙',
};

const STATUS_FULL = {
  'Available': '✅ Available',
  'Doubt': '❓ Doubt',
  'Injury': '❌ Injury',
  'Red card': '🟥 Red card',
  'Yellow red card': '🟥 Yellow/red card',
  'Last Yellow card': '🟨 Last Yellow card',
  'Not playing (Called up)': '✈️ Not playing (Called up)',
  'Not playing (Other)': '🚫 Not playing (Other)',
  'Return (Injury)': '🔙 Return (Injury)',
  'Return (Susp)': '🔙 Return (Susp)',
  'Return (Called up)': '🔙 Return (Called up)',
  'Return (Other)': '🔙 Return (Other)',
};

function collapseSelect(s) {
  var opt = s.options[s.selectedIndex];
  var val = s.value;
  if (STATUS_EMOJI[val]) {
    opt.textContent = STATUS_EMOJI[val];
  }
  s.style.width = '32px';
}

function expandSelect(s) {
  var val = s.value;
  for (var i = 0; i < s.options.length; i++) {
    var v = s.options[i].value;
    if (STATUS_FULL[v]) s.options[i].textContent = STATUS_FULL[v];
  }
  s.style.width = '170px';
}

function updateStatusIcon(s) {
  var row = s.closest('tr');
  if (!row) return;
  var player = row.querySelector('td.player-name');
  if (!player) return;
  player.classList.remove('status-red', 'status-green', 'status-orange');
  var x = ['Injury', 'Red card', 'Yellow red card', 'Not playing (Called up)', 'Not playing (Other)'];
  var g = ['Return (Injury)', 'Return (Susp)', 'Return (Called up)', 'Return (Other)'];
  var o = ['Doubt'];
  if (x.indexOf(s.value) !== -1) player.classList.add('status-red');
  else if (g.indexOf(s.value) !== -1) player.classList.add('status-green');
  else if (o.indexOf(s.value) !== -1) player.classList.add('status-orange');
  collapseSelect(s);
}

// Init all selects on page load
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.status-select').forEach(function (s) {
    collapseSelect(s);
    s.addEventListener('focus', function () { expandSelect(s); });
    s.addEventListener('blur', function () { collapseSelect(s); });
    s.addEventListener('change', function () { updateStatusIcon(s); });
  });
});
