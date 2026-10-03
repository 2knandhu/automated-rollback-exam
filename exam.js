(() => {
  let current = 0;
  let answers = {};
  let remaining = Number(window.REMAINING || 0);
  const examId = Number(window.EXAM_ID);
  const questions = [...document.querySelectorAll(".question")];
  const timer = document.getElementById("timer");
  const saveBox = document.getElementById("save");
  const popup = document.getElementById("popup");
  const rollbackButton = document.getElementById("rollback");
  const cancelRollback = document.getElementById("cancelRollback");
  const failureButton = document.getElementById("failure");
  const form = document.getElementById("examForm");
  let timerHandle = null;
  let saveInProgress = false;

  const initial = window.CHECKPOINT || {};
  answers = initial.answers || {};
  current = Number(initial.current_question || 0);
  if (initial.remaining_time !== undefined && initial.remaining_time !== null) {
    remaining = Number(initial.remaining_time);
  }

  function localKey() { return "exam_" + examId; }

  function collectAnswers() {
    document.querySelectorAll('input[type="radio"]:checked').forEach(input => {
      answers[input.name.replace(/^q/, "")] = Number(input.value);
    });
    return answers;
  }

  function restoreAnswers() {
    Object.entries(answers).forEach(([qid, value]) => {
      const input = document.querySelector(
        'input[name="q' + CSS.escape(qid) + '"][value="' + Number(value) + '"]'
      );
      if (input) input.checked = true;
    });
  }

  function updateQuestionButtons() {
    document.querySelectorAll(".qbtn").forEach((button, i) => {
      button.classList.toggle("active", i === current);
      const qid = questions[i]?.dataset.qid;
      button.classList.toggle("answered", qid && Object.prototype.hasOwnProperty.call(answers, qid));
    });
    document.getElementById("prev").disabled = current <= 0;
    document.getElementById("next").disabled = current >= questions.length - 1;
    document.getElementById("progressText").textContent =
      "Question " + (current + 1) + " of " + questions.length;
    document.getElementById("progressBar").style.width =
      (((current + 1) / Math.max(questions.length, 1)) * 100) + "%";
  }

  function showQuestion(index) {
    if (!questions.length) return;
    current = Math.max(0, Math.min(index, questions.length - 1));
    questions.forEach((question, i) => {
      question.style.display = i === current ? "block" : "none";
    });
    updateQuestionButtons();
  }

  function createQuestionButtons() {
    const container = document.getElementById("qbuttons");
    container.innerHTML = "";
    questions.forEach((question, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "qbtn";
      button.textContent = index + 1;
      button.setAttribute("aria-label", "Go to question " + (index + 1));
      button.addEventListener("click", () => {
        collectAnswers();
        showQuestion(index);
        saveCheckpoint();
      });
      container.appendChild(button);
    });
  }

  async function saveCheckpoint() {
    if (saveInProgress || !form) return;
    saveInProgress = true;
    collectAnswers();
    const data = {
      current_question: current,
      answers,
      remaining_time: remaining
    };
    try { localStorage.setItem(localKey(), JSON.stringify(data)); } catch (_) {}
    saveBox.textContent = "Saving checkpoint…";
    try {
      const response = await fetch("/api/checkpoint", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ exam_id: examId, ...data })
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error("Checkpoint was not saved on server");
      saveBox.textContent = "✓ Checkpoint saved";
    } catch (_) {
      saveBox.textContent = "⚠ Checkpoint saved in this browser; server connection unavailable";
    } finally {
      saveInProgress = false;
      updateQuestionButtons();
    }
  }

  function rollbackFromLocalStorage() {
    try {
      const raw = localStorage.getItem(localKey());
      if (!raw) {
        saveBox.textContent = "⚠ No local checkpoint is available";
        return;
      }
      const saved = JSON.parse(raw);
      answers = saved.answers || {};
      remaining = Number(saved.remaining_time || remaining);
      restoreAnswers();
      showQuestion(Number(saved.current_question || 0));
      saveBox.textContent = "✓ Local checkpoint restored — exam resumed";
    } catch (_) {
      saveBox.textContent = "⚠ Could not restore local checkpoint";
    }
  }

  async function rollbackExam() {
    popup.style.display = "none";
    saveBox.textContent = "Restoring last valid checkpoint…";
    try {
      const response = await fetch("/api/failure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ exam_id: examId, failure_type: "Simulated failure or network interruption" })
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error("Server rollback unavailable");
      answers = data.answers || {};
      current = Number(data.current_question || 0);
      remaining = Number(data.remaining_time || 0);
      restoreAnswers();
      showQuestion(current);
      saveBox.textContent = "✓ Rollback successful — exam resumed";
      try { localStorage.setItem(localKey(), JSON.stringify({ current_question: current, answers, remaining_time: remaining })); } catch (_) {}
      updateTimerDisplay();
    } catch (_) {
      rollbackFromLocalStorage();
    }
  }

  function updateTimerDisplay() {
    const mins = Math.floor(Math.max(remaining, 0) / 60);
    const secs = Math.max(remaining, 0) % 60;
    timer.textContent = String(mins).padStart(2, "0") + ":" + String(secs).padStart(2, "0");
  }

  function tick() {
    updateTimerDisplay();
    if (remaining <= 0) {
      collectAnswers();
      document.getElementById("answers").value = JSON.stringify(answers);
      form.submit();
      return;
    }
    remaining -= 1;
  }

  document.getElementById("prev").addEventListener("click", () => {
    collectAnswers();
    showQuestion(current - 1);
    saveCheckpoint();
  });
  document.getElementById("next").addEventListener("click", () => {
    collectAnswers();
    showQuestion(current + 1);
    saveCheckpoint();
  });

  document.querySelectorAll('input[type="radio"]').forEach(input => {
    input.addEventListener("change", () => {
      collectAnswers();
      updateQuestionButtons();
      saveCheckpoint();
    });
  });

  failureButton.addEventListener("click", async () => {
    await saveCheckpoint();
    popup.style.display = "flex";
  });
  rollbackButton.addEventListener("click", rollbackExam);
  cancelRollback.addEventListener("click", () => { popup.style.display = "none"; });

  window.addEventListener("offline", () => {
    collectAnswers();
    try { localStorage.setItem(localKey(), JSON.stringify({ current_question: current, answers, remaining_time: remaining })); } catch (_) {}
    saveBox.textContent = "⚠ Internet disconnected — local checkpoint preserved";
  });
  window.addEventListener("online", () => {
    saveBox.textContent = "✓ Internet restored — syncing checkpoint";
    saveCheckpoint();
  });
  window.addEventListener("beforeunload", () => {
    collectAnswers();
    try { localStorage.setItem(localKey(), JSON.stringify({ current_question: current, answers, remaining_time: remaining })); } catch (_) {}
  });

  form.addEventListener("submit", event => {
    collectAnswers();
    document.getElementById("answers").value = JSON.stringify(answers);
    if (timerHandle) clearInterval(timerHandle);
  });

  createQuestionButtons();
  restoreAnswers();
  showQuestion(current);
  updateTimerDisplay();
  timerHandle = setInterval(tick, 1000);
  setInterval(saveCheckpoint, 10000);
})();
