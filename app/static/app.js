const form = document.getElementById('upload-form');
const statusCard = document.getElementById('status-card');
const statusBox = document.getElementById('status');
const results = document.getElementById('results');

function setStatus(message) {
  statusCard.hidden = false;
  statusBox.textContent = message;
}

function showResult(data) {
  results.hidden = false;
  document.getElementById('meta').textContent = `Language: ${data.language || 'unknown'} | Duration: ${data.duration ? data.duration.toFixed(1) + 's' : 'unknown'} | File: ${data.filename}`;
  document.getElementById('summary').textContent = data.summary || 'No summary generated.';
  document.getElementById('transcript').textContent = data.text || '';
  document.getElementById('keywords').innerHTML = (data.keywords || []).map(k => `<span>${k}</span>`).join('');
  document.getElementById('exports').innerHTML = Object.entries(data.exports || {})
    .map(([kind, url]) => `<a href="${url}">${kind.toUpperCase()}</a>`).join('');
}

async function transcribeBlob(blob, filename) {
  const data = new FormData();
  data.append('file', blob, filename);
  data.append('model_size', document.getElementById('model-size').value);
  setStatus('Transcribing locally. First run may download a Whisper model...');
  const response = await fetch('/api/transcribe', { method: 'POST', body: data });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Transcription failed');
  setStatus('Done.');
  showResult(payload);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = document.getElementById('file').files[0];
  if (!file) return;
  try { await transcribeBlob(file, file.name); }
  catch (error) { setStatus(error.message); }
});

let recorder;
let chunks = [];
const recordButton = document.getElementById('record');
const stopButton = document.getElementById('stop');
const recordingStatus = document.getElementById('recording-status');

recordButton.addEventListener('click', async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = event => chunks.push(event.data);
  recorder.onstop = async () => {
    stream.getTracks().forEach(track => track.stop());
    recordingStatus.textContent = 'Uploading recording...';
    await transcribeBlob(new Blob(chunks, { type: 'audio/webm' }), 'recording.webm');
    recordingStatus.textContent = 'Idle';
  };
  recorder.start();
  recordButton.disabled = true;
  stopButton.disabled = false;
  recordingStatus.textContent = 'Recording...';
});

stopButton.addEventListener('click', () => {
  stopButton.disabled = true;
  recordButton.disabled = false;
  recorder.stop();
});
