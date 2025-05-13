// Estado global de la aplicación
const AppState = {
    sidebarOpen: true,
    isRecording: false,
    mediaRecorder: null,
    audioChunks: []
};

// Funciones de grabación
async function startRecording() {
    console.log("🔵 startRecording() ejecutado"); 
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log("✅ Micrófono accedido correctamente", stream);

        console.log("🎥 Soporta MediaRecorder:", typeof MediaRecorder !== 'undefined');
        console.log("🎧 Soporta audio/webm:", MediaRecorder.isTypeSupported('audio/webm;codecs=opus'));

        const options = { mimeType: 'audio/webm;codecs=opus' };
        if (!MediaRecorder.isTypeSupported(options.mimeType)) {
            console.warn('⚠️ Tipo MIME no soportado, usando por defecto');
            AppState.mediaRecorder = new MediaRecorder(stream);
        } else {
            AppState.mediaRecorder = new MediaRecorder(stream, options);
        }

        AppState.audioChunks = [];
        AppState.isRecording = true;

        updateRecordingUI(true);
        console.log("🎙️ Grabación iniciada");

        AppState.mediaRecorder.ondataavailable = event => {
            AppState.audioChunks.push(event.data);
            console.log("📥 Chunk recibido:", event.data);
        };

        AppState.mediaRecorder.onstop = () => {
            AppState.isRecording = false;
            updateRecordingUI(false);
            console.log("⛔ Grabación detenida");
        };

        AppState.mediaRecorder.start();
    } catch (error) {
        console.error('❌ Error al acceder al micrófono:', error);
        alert('No se pudo acceder al micrófono. Por favor, verifica los permisos.');
    }
}


function stopRecording() {
    if (AppState.mediaRecorder && AppState.isRecording) {
        AppState.mediaRecorder.stop();
        AppState.mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
}

function sendRecording() {
    if (AppState.audioChunks.length === 0) {
        alert('No hay grabación para enviar. Graba algo primero.');
        return;
    }

    const audioBlob = new Blob(AppState.audioChunks, { type: 'audio/webm' });
    sendAudio(audioBlob);
}

function updateRecordingUI(isRecording) {
    const startBtn = document.querySelector('.tab:nth-child(1)');
    const stopBtn = document.querySelector('.tab:nth-child(2)');
    const sendBtn = document.querySelector('.tab:nth-child(3)');

    if (!startBtn || !stopBtn || !sendBtn) {
        console.warn("⚠️ No se encontraron botones para actualizar UI");
        return;
    }

    if (isRecording) {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        sendBtn.disabled = true;
    } else {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        sendBtn.disabled = false;
    }
}


function setupRecordingControls() {
    const startBtn = document.querySelector('.controls button:nth-child(1)');
    const stopBtn = document.querySelector('.controls button:nth-child(2)');
    const sendBtn = document.querySelector('.controls button:nth-child(3)');

    startBtn.addEventListener('click', startRecording);
    stopBtn.addEventListener('click', stopRecording);
    sendBtn.addEventListener('click', sendRecording);

    stopBtn.disabled = true;
    sendBtn.disabled = true;
}

async function sendAudio(blob) {
    const formData = new FormData();
    formData.append('audio', blob, 'grabacion.webm');

    const sourceLang = document.getElementById('source-lang')?.value;
    const targetLang = document.getElementById('target-lang')?.value;

    formData.append('source_lang', sourceLang);
    formData.append('target_lang', targetLang);

    try {
        const response = await fetch('/procesar_audio', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        // Mostrar texto reconocido
        document.getElementById('recognized-text').textContent =
            result.texto && result.texto.trim() !== ''
                ? `${result.texto}`
                : '⚠️ No se reconoció texto. Intenta hablar más claro o más tiempo.';

        // Mostrar traducción
        document.getElementById('translated-text').textContent =
            result.traduccion && result.traduccion.trim() !== ''
                ? `${result.traduccion}`
                : '⚠️ Sin traducción disponible porque no hubo texto reconocido.';

        // Configurar audio traducido
        if (result.audio_url) {
            const audioPlayer = document.getElementById('audio-player');
            const playButton = document.getElementById('play-audio');
            const container = document.getElementById('audio-container');

            audioPlayer.src = result.audio_url;
            container.style.display = 'block';
            audioPlayer.load();

            playButton.onclick = () => {
                audioPlayer.play();
            };
        } else {
            document.getElementById('audio-container').style.display = 'none';
        }


    } catch (error) {
        console.error('Error al procesar el audio:', error);
        document.getElementById('recognized-text').textContent = 'Error al procesar el audio';
        document.getElementById('translated-text').textContent = '';
        alert('Ocurrió un error al procesar el audio. Por favor, intenta nuevamente.');
    }
}

