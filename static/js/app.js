/**
* Copyright 2025 Google LLC
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/

/**
 * app.js: JS code for the adk-streaming sample app.
 */

/**
 * WebSocket handling
 */

// Connect the server with a WebSocket connection
const sessionId = Math.random().toString().substring(10);
const ws_url =
  "ws://" + window.location.host + "/ws/" + sessionId;
let websocket = null;
let is_audio = false;

// Get DOM elements
const messageForm = document.getElementById("messageForm");
const messageInput = document.getElementById("message");
const messagesDiv = document.getElementById("messages");
let currentMessageId = null;

// WebSocket handlers
function connectWebsocket() {
  // Connect websocket
  websocket = new WebSocket(ws_url + "?is_audio=" + is_audio);

  // Handle connection open
  websocket.onopen = function () {
    // Connection opened messages
    console.log("WebSocket connection opened.");
    document.getElementById("messages").textContent = "Connection opened";

    // Enable the Send button
    document.getElementById("sendButton").disabled = false;
    addSubmitHandler();
  };

  // Handle incoming messages
  websocket.onmessage = function (event) {
    // Parse the incoming message
    const message_from_server = JSON.parse(event.data);
    console.log("[AGENT TO CLIENT] ", message_from_server);

    // Check if the turn is complete
    // if turn complete, add new message
    if (
      message_from_server.turn_complete &&
      message_from_server.turn_complete == true
    ) {
      currentMessageId = null;
      return;
    }

    // Check for interrupt message
    if (
      message_from_server.interrupted &&
      message_from_server.interrupted === true
    ) {
      // Stop audio playback if it's playing
      if (audioPlayerNode) {
        audioPlayerNode.port.postMessage({ command: "endOfAudio" });
      }
      return;
    }

    // If it's audio, play it
    if (message_from_server.mime_type == "audio/pcm" && audioPlayerNode) {
      audioPlayerNode.port.postMessage(base64ToArray(message_from_server.data));
    }

    // If it's a text, print it
    if (message_from_server.mime_type == "text/plain") {
      // add a new message for a new turn
      if (currentMessageId == null) {
        currentMessageId = Math.random().toString(36).substring(7);
        const message = document.createElement("p");
        message.id = currentMessageId;
        // Append the message element to the messagesDiv
        messagesDiv.appendChild(message);
      }

      // Add message text to the existing message element
      const message = document.getElementById(currentMessageId);
      message.textContent += message_from_server.data;

      // Scroll down to the bottom of the messagesDiv
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
  };

  // Handle connection close
  websocket.onclose = function () {
    console.log("WebSocket connection closed.");
    document.getElementById("sendButton").disabled = true;
    document.getElementById("messages").textContent = "Connection closed";
    setTimeout(function () {
      console.log("Reconnecting...");
      connectWebsocket();
    }, 5000);
  };

  websocket.onerror = function (e) {
    console.log("WebSocket error: ", e);
  };
}
connectWebsocket();

// Add submit handler to the form
function addSubmitHandler() {
  messageForm.onsubmit = function (e) {
    e.preventDefault();
    const message = messageInput.value;
    if (message) {
      const p = document.createElement("p");
      p.textContent = "> " + message;
      messagesDiv.appendChild(p);
      messageInput.value = "";
      sendMessage({
        mime_type: "text/plain",
        data: message,
      });
      console.log("[CLIENT TO AGENT] " + message);
    }
    return false;
  };
}

// Send a message to the server as a JSON string
function sendMessage(message) {
  if (websocket && websocket.readyState == WebSocket.OPEN) {
    const messageJson = JSON.stringify(message);
    websocket.send(messageJson);
  }
}

// Decode Base64 data to Array
function base64ToArray(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

/**
 * Audio handling
 */

let audioPlayerNode;
let audioPlayerContext;
let audioRecorderNode;
let audioRecorderContext;
let micStream;

// Audio buffering for 0.2s intervals
let audioBuffer = [];
let bufferTimer = null;

// Import the audio worklets
import { startAudioPlayerWorklet } from "./audio-player.js";
import { startAudioRecorderWorklet } from "./audio-recorder.js";

// Start audio
function startAudio() {
  // Start audio output
  startAudioPlayerWorklet().then(([node, ctx]) => {
    audioPlayerNode = node;
    audioPlayerContext = ctx;
  });
  // Start audio input
  startAudioRecorderWorklet(audioRecorderHandler).then(
    ([node, ctx, stream]) => {
      audioRecorderNode = node;
      audioRecorderContext = ctx;
      micStream = stream;
    }
  );
}

// Start the audio only when the user clicked the button
// (due to the gesture requirement for the Web Audio API)
const startAudioButton = document.getElementById("startAudioButton");
startAudioButton.addEventListener("click", () => {
  startAudioButton.disabled = true;
  startAudio();
  is_audio = true;
  connectWebsocket(); // reconnect with the audio mode
});

// Audio recorder handler
function audioRecorderHandler(pcmData) {
  // Add audio data to buffer
  audioBuffer.push(new Uint8Array(pcmData));
  
  // Start timer if not already running
  if (!bufferTimer) {
    bufferTimer = setInterval(sendBufferedAudio, 200); // 0.2 seconds
  }
}

// Send buffered audio data every 0.2 seconds
function sendBufferedAudio() {
  if (audioBuffer.length === 0) {
    return;
  }
  
  // Calculate total length
  let totalLength = 0;
  for (const chunk of audioBuffer) {
    totalLength += chunk.length;
  }
  
  // Combine all chunks into a single buffer
  const combinedBuffer = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of audioBuffer) {
    combinedBuffer.set(chunk, offset);
    offset += chunk.length;
  }
  
  // Send the combined audio data
  sendMessage({
    mime_type: "audio/pcm",
    data: arrayBufferToBase64(combinedBuffer.buffer),
  });
  console.log("[CLIENT TO AGENT] sent %s bytes", combinedBuffer.byteLength);
  
  // Clear the buffer
  audioBuffer = [];
}

// Stop audio recording and cleanup
function stopAudioRecording() {
  if (bufferTimer) {
    clearInterval(bufferTimer);
    bufferTimer = null;
  }
  
  // Send any remaining buffered audio
  if (audioBuffer.length > 0) {
    sendBufferedAudio();
  }
}

// Encode an array buffer with Base64
function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

// ==================================================================
// NEW: Video Sharing Functionality
// ==================================================================
const shareVideoButton = document.getElementById('shareVideoButton');
const videoFeed = document.getElementById('videoFeed');
const captureCanvas = document.getElementById('captureCanvas');
const sentFrameCanvas = document.getElementById('sentFrameCanvas');
const fpsInput = document.getElementById('fpsInput');

let videoStream = null;
let frameSenderInterval = null;
let isVideoSharing = false;

// Add event listener to the video share button
shareVideoButton.addEventListener('click', toggleVideoSharing);

async function toggleVideoSharing() {
    if (!isVideoSharing) {
        // ---- Start Sharing ----
        try {
            // Get user's camera stream
            videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
            videoFeed.srcObject = videoStream;
            videoFeed.style.display = 'block';

            // Start sending frames at the specified FPS
            const fps = parseInt(fpsInput.value, 10);
            const interval = 1000 / fps;
            frameSenderInterval = setInterval(sendVideoFrame, interval);

            shareVideoButton.textContent = 'Stop Sharing';
            isVideoSharing = true;
            console.log(`Video sharing started at ${fps} FPS.`);

        } catch (error) {
            console.error("Error accessing camera:", error);
            alert("Could not access the camera. Please check permissions.");
        }
    } else {
        // ---- Stop Sharing ----
        if (videoStream) {
            videoStream.getTracks().forEach(track => track.stop());
        }
        if (frameSenderInterval) {
            clearInterval(frameSenderInterval);
        }
        
        videoFeed.srcObject = null;
        shareVideoButton.textContent = 'Share Video';
        isVideoSharing = false;
        console.log("Video sharing stopped.");
        
        // Clear the last sent frame canvas
        const ctx = sentFrameCanvas.getContext('2d');
        ctx.clearRect(0, 0, sentFrameCanvas.width, sentFrameCanvas.height);
    }
}

function sendVideoFrame() {
    if (!videoStream || videoFeed.paused || videoFeed.ended) {
        return;
    }

    const captureCtx = captureCanvas.getContext('2d');
    const sentFrameCtx = sentFrameCanvas.getContext('2d');
    
    // Set canvas dimensions to match video to avoid distortion
    const videoWidth = videoFeed.videoWidth;
    const videoHeight = videoFeed.videoHeight;
    if (captureCanvas.width !== videoWidth || captureCanvas.height !== videoHeight) {
        captureCanvas.width = videoWidth;
        captureCanvas.height = videoHeight;
        sentFrameCanvas.width = videoWidth;
        sentFrameCanvas.height = videoHeight;
    }
    
    // Draw the current video frame onto the hidden canvas
    captureCtx.drawImage(videoFeed, 0, 0, videoWidth, videoHeight);

    // Draw the captured frame to the visible canvas for user feedback
    sentFrameCtx.drawImage(captureCanvas, 0, 0, videoWidth, videoHeight);
    
    // Get the frame as a JPEG image in Base64
    // The quality parameter (0.7) can be adjusted to balance quality and file size
    const dataUrl = captureCanvas.toDataURL('image/jpeg', 0.7);
    const base64Data = dataUrl.split(',')[1];

    // Send the frame data over the WebSocket
    sendMessage({
        mime_type: 'image/jpeg',
        data: base64Data,
    });

    console.log(`[CLIENT TO AGENT] Sent video frame (${base64Data.length} bytes)`);
}