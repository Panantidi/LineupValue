const STATUS_EMOJI = {
  'Available': '\u2705',
  'Doubt': '\u2754',
  'Injury': '\u274C',
  'Red card': '\uD83D\uDFE5',
  'Yellow red card': '\uD83D\uDFE5',
  'Last Yellow card': '\uD83D\uDFE8',
  'Not playing (Called up)': '\u2708\uFE0F',
  'Not playing (Other)': '\uD83D\uDEAB',
  'Return (Injury)': '\uD83D\uDD04',
  'Return (Susp)': '\uD83D\uDD04',
  'Return (Called up)': '\uD83D\uDD04',
  'Return (Other)': '\uD83D\uDD04',
};

function updateStatusIcon(s){
  var cell = s.parentElement;
  var emoji = cell.querySelector('.status-emoji');
  if(emoji && STATUS_EMOJI[s.value]){
    emoji.textContent = STATUS_EMOJI[s.value];
  }
  var row = s.closest('tr');
  if(!row) return;
  var player = row.querySelector('td.player-name');
  if(!player) return;
  player.classList.remove('status-red','status-green','status-orange');
  var x = ['Injury','Red card','Yellow red card','Not playing (Called up)','Not playing (Other)'];
  var g = ['Return (Injury)','Return (Susp)','Return (Called up)','Return (Other)'];
  var o = ['Doubt'];
  if(x.indexOf(s.value) !== -1) player.classList.add('status-red');
  else if(g.indexOf(s.value) !== -1) player.classList.add('status-green');
  else if(o.indexOf(s.value) !== -1) player.classList.add('status-orange');
}
