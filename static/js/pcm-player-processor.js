/**
 * An audio worklet processor that stores the PCM audio data sent from the main thread
 * to a buffer and plays it.
 */
class PCMPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // Init buffer - use dynamic size based on actual sample rate
    const sampleRate = this.sampleRate || 48000; // Default fallback
    this.bufferSize = sampleRate * 180;  // Sample rate x 180 seconds
    this.buffer = new Float32Array(this.bufferSize);
    this.writeIndex = 0;
    this.readIndex = 0;

    console.log(`PCM Player: Using sample rate ${sampleRate}, buffer size ${this.bufferSize}`);

    // Handle incoming messages from main thread
    this.port.onmessage = (event) => {
      // Reset the buffer when 'endOfAudio' message received
      if (event.data.command === 'endOfAudio') {
        this.writeIndex = 0;
        this.readIndex = 0;
        console.log("PCM Player: Buffer reset");
        return;
      }

      // Decode the base64 data to int16 array.
      const int16Samples = new Int16Array(event.data);

      // Add the audio data to the buffer
      this._enqueue(int16Samples);
    };
  }

  // Push incoming Int16 data into our ring buffer.
  _enqueue(int16Samples) {
    for (let i = 0; i < int16Samples.length; i++) {
      // Convert 16-bit integer to float in [-1, 1]
      const floatVal = int16Samples[i] / 32768;
      
      this.buffer[this.writeIndex] = floatVal;
      this.writeIndex = (this.writeIndex + 1) % this.bufferSize;
    }
  }

  // The system calls `process()` ~128 samples at a time (depending on the browser).
  // We fill the output buffers from our ring buffer.
  process(inputs, outputs, parameters) {
    // Write a frame to the output
    const output = outputs[0];
    const framesPerBlock = output[0].length;
    
    for (let frame = 0; frame < framesPerBlock; frame++) {
      const sample = this.buffer[this.readIndex];
      
      // Write to all output channels
      for (let channel = 0; channel < output.length; channel++) {
        output[channel][frame] = sample;
      }
      
      this.readIndex = (this.readIndex + 1) % this.bufferSize;
    }

    // Returning true tells the system to keep the processor alive
    return true;
  }
}

registerProcessor('pcm-player-processor', PCMPlayerProcessor);