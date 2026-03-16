/**
 * Utilities for handling PCM audio data for the Gemini Live API.
 */

export class AudioProcessor {
  private audioContext: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private processor: ScriptProcessorNode | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private recordingVersion = 0;

  async startRecording(onAudioData: (base64Data: string) => void) {
    this.stopRecording();
    const version = ++this.recordingVersion;

    const audioContext = new AudioContext({ sampleRate: 16000 });
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const source = audioContext.createMediaStreamSource(stream);

    this.audioContext = audioContext;
    this.stream = stream;
    this.source = source;

    try {
      await audioContext.audioWorklet.addModule(
        new URL('./worklets/pcm-capture-worklet.js', import.meta.url)
      );
      if (version !== this.recordingVersion) return;

      this.workletNode = new AudioWorkletNode(audioContext, 'pcm-capture-worklet');
      this.workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        const base64Data = this.arrayBufferToBase64(event.data);
        onAudioData(base64Data);
      };
      source.connect(this.workletNode);
      return;
    } catch (error) {
      console.warn('AudioWorklet unavailable, falling back to ScriptProcessorNode.', error);
    }

    if (version !== this.recordingVersion) return;

    this.processor = audioContext.createScriptProcessor(4096, 1, 1);
    this.processor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);
      const pcmData = this.float32ToInt16(inputData);
      onAudioData(this.arrayBufferToBase64(pcmData.buffer));
    };
    source.connect(this.processor);
    this.processor.connect(audioContext.destination);
  }

  stopRecording() {
    this.recordingVersion++;
    this.workletNode?.disconnect();
    this.workletNode = null;
    this.processor?.disconnect();
    this.processor = null;
    this.source?.disconnect();
    this.source = null;
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
    this.audioContext?.close();
    this.audioContext = null;
  }

  private float32ToInt16(buffer: Float32Array): Int16Array {
    const l = buffer.length;
    const buf = new Int16Array(l);
    for (let i = 0; i < l; i++) {
      const s = Math.max(-1, Math.min(1, buffer[i]));
      buf[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return buf;
  }

  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  }
}

export class AudioPlayer {
  private audioContext: AudioContext | null = null;
  private nextStartTime: number = 0;

  constructor() {
    this.audioContext = new AudioContext({ sampleRate: 24000 });
  }

  playChunk(base64Data: string) {
    if (!this.audioContext) return;
    if (!base64Data || typeof base64Data !== 'string') return;

    let binaryString = "";
    try {
      const normalizedBase64 = this.normalizeBase64(base64Data);
      binaryString = window.atob(normalizedBase64);
    } catch (err) {
      console.warn("Skipping invalid audio chunk from backend.", err);
      return;
    }
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    const int16Data = new Int16Array(bytes.buffer);
    const float32Data = new Float32Array(int16Data.length);
    for (let i = 0; i < int16Data.length; i++) {
      float32Data[i] = int16Data[i] / 32768.0;
    }

    const audioBuffer = this.audioContext.createBuffer(1, float32Data.length, 24000);
    audioBuffer.getChannelData(0).set(float32Data);

    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.audioContext.destination);

    const currentTime = this.audioContext.currentTime;
    if (this.nextStartTime < currentTime) {
      this.nextStartTime = currentTime;
    }

    source.start(this.nextStartTime);
    this.nextStartTime += audioBuffer.duration;
  }

  stop() {
    this.audioContext?.close();
    this.audioContext = new AudioContext({ sampleRate: 24000 });
    this.nextStartTime = 0;
  }

  private normalizeBase64(input: string): string {
    const sanitized = input.replace(/-/g, '+').replace(/_/g, '/').replace(/\s/g, '');
    const padding = sanitized.length % 4;
    if (padding === 0) return sanitized;
    return sanitized + '='.repeat(4 - padding);
  }
}
