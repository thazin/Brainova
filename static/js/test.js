// ── Password toggle ──────────────────────────────────────────────────────────
function togglePassword(inputId, btn) {
  var input = document.getElementById(inputId);
  var icon  = btn.querySelector('i');
  if (input.type === 'password') {
    input.type     = 'text';
    icon.className = 'bi bi-eye-slash';
  } else {
    input.type     = 'password';
    icon.className = 'bi bi-eye';
  }
}

// ── Test state ────────────────────────────────────────────────────────────────
var currentQuestion  = 1;
var totalQuestions   = 0;
var answeredById     = {};   // { questionId: true }
var answeredByIndex  = {};   // { questionIndex: true }

// ── Init (called from take.html) ─────────────────────────────────────────────
function initTest(total, timerSeconds) {
  totalQuestions = total;
  updateNavGrid();
  updateNavButtons();
  startTimer(timerSeconds);
  // mark nav btn 1 as current
  var first = document.getElementById('nav-btn-1');
  if (first) first.classList.replace('btn-outline-secondary', 'btn-primary');
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goToQuestion(n) {
  if (n < 1 || n > totalQuestions) return;

  document.getElementById('qcard-' + currentQuestion).style.display = 'none';
  currentQuestion = n;
  document.getElementById('qcard-' + currentQuestion).style.display = 'block';

  document.getElementById('question-counter').textContent =
    'Question ' + currentQuestion + ' of ' + totalQuestions;

  updateNavButtons();
  updateNavGrid();
}

function prevQuestion() {
  if (currentQuestion > 1) goToQuestion(currentQuestion - 1);
}

function nextQuestion() {
  if (currentQuestion < totalQuestions) goToQuestion(currentQuestion + 1);
}

function jumpToQuestion() {
  var input = document.getElementById('jumpInput');
  var n = parseInt(input.value, 10);
  if (!isNaN(n) && n >= 1 && n <= totalQuestions) {
    goToQuestion(n);
    input.value = '';
  } else {
    input.classList.add('is-invalid');
    setTimeout(function () { input.classList.remove('is-invalid'); }, 1200);
  }
}

// Allow pressing Enter in the jump input
document.addEventListener('DOMContentLoaded', function () {
  var jumpInput = document.getElementById('jumpInput');
  if (jumpInput) {
    jumpInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); jumpToQuestion(); }
    });
  }
});

// ── Update helpers ────────────────────────────────────────────────────────────
function updateNavButtons() {
  var prevBtn = document.getElementById('prevBtn');
  var nextBtn = document.getElementById('nextBtn');
  if (prevBtn) prevBtn.disabled = (currentQuestion === 1);
  if (nextBtn) nextBtn.disabled = (currentQuestion === totalQuestions);
}

function updateNavGrid() {
  for (var i = 1; i <= totalQuestions; i++) {
    var btn = document.getElementById('nav-btn-' + i);
    if (!btn) continue;
    btn.classList.remove('btn-primary', 'btn-success', 'btn-outline-secondary');
    if (i === currentQuestion) {
      btn.classList.add('btn-primary');
    } else if (answeredByIndex[i]) {
      btn.classList.add('btn-success');
    } else {
      btn.classList.add('btn-outline-secondary');
    }
  }
}

// ── Answer tracking ───────────────────────────────────────────────────────────
function onAnswer(questionId, questionIndex, total) {
  answeredById[questionId]       = true;
  answeredByIndex[questionIndex] = true;

  var answered = Object.keys(answeredById).length;
  var pct      = Math.round((answered / total) * 100);

  var bar = document.getElementById('progress-bar');
  var txt = document.getElementById('progress-text');
  if (bar) bar.style.width = pct + '%';
  if (txt) txt.textContent = answered + ' / ' + total + ' answered';

  var hint = document.getElementById('submit-hint');
  if (hint) {
    if (answered === total) {
      hint.textContent  = 'All questions answered — ready to submit!';
      hint.className    = 'text-success mb-3';
    } else {
      hint.textContent  = (total - answered) + ' question(s) remaining.';
      hint.className    = 'text-muted mb-3';
    }
  }

  updateNavGrid();
}

function confirmSubmit(total) {
  var answered = Object.keys(answeredById).length;
  if (answered < total) {
    return confirm(
      'You have ' + (total - answered) + ' unanswered question(s).\n' +
      'Unanswered questions will be marked as wrong.\n\nSubmit anyway?'
    );
  }
  return true;
}

// ── Countdown timer ───────────────────────────────────────────────────────────
function startTimer(seconds) {
  var remaining = seconds;

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  function tick() {
    var mins = Math.floor(remaining / 60);
    var secs = remaining % 60;
    var display = document.getElementById('timer-display');
    var box     = document.getElementById('timer-box');
    if (display) display.textContent = pad(mins) + ':' + pad(secs);

    if (box) {
      box.classList.remove('timer-warning', 'timer-danger');
      if (remaining <= 60)       box.classList.add('timer-danger');
      else if (remaining <= 300) box.classList.add('timer-warning');
    }

    if (remaining <= 0) {
      clearInterval(interval);
      alert('Time is up! Your answers will be submitted now.');
      document.getElementById('testForm').submit();
      return;
    }
    remaining--;
  }

  tick(); // immediate first render
  var interval = setInterval(tick, 1000);
}
