class PcmCaptureWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunkSize = 2048;
    this.offset = 0;
    this.chunk = new Int16Array(this.chunkSize);
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) {
      return true;
    }

    const channelData = input[0];
    for (let i = 0; i < channelData.length; i++) {
      const s = Math.max(-1, Math.min(1, channelData[i]));
      this.chunk[this.offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;

      if (this.offset >= this.chunkSize) {
        this.port.postMessage(this.chunk.buffer.slice(0), [this.chunk.buffer]);
        this.chunk = new Int16Array(this.chunkSize);
        this.offset = 0;
      }
    }

    return true;
  }
}

registerProcessor('pcm-capture-worklet', PcmCaptureWorklet);
