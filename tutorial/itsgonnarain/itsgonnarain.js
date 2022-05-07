let PATTERNS = []

const planeStartPolyrhytm = [
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10},
    {"start": 0, "duration": 1, "rateDiv": 10}
]
PATTERNS.push(planeStartPolyrhytm)

const collage = (soundsAmount=10) => {
    let retArr = [];
    [...Array(soundsAmount).keys()].forEach((num) => {
        retArr.push({"start": 0, "duration": num, "rateDiv": 10})
    })
    console.log(retArr)
    return retArr
}
PATTERNS.push(collage(5))


const SOUNDS = ['metronome2ch.wav', '1khzmetronome.flac', 'troche seler.wav']
const SOUND = SOUNDS[2]

let PLAYING_AUDIO = []
let audioContext = new AudioContext();
var wave = new Wave();
var canvas = document.getElementById("wave");
wave.fromElement(PLAYING_AUDIO[0], canvas, {
        type: ["bars"]
});

function startLoop(audioBuffer, loopStart, duration, rate=1, pan=0) {
    let sourceNode = audioContext.createBufferSource();
    let pannerNode = audioContext.createStereoPanner();
    sourceNode.buffer = audioBuffer;
    sourceNode.loop = true;

    // loop logic
    sourceNode.loopStart = loopStart;
    sourceNode.loopEnd = loopStart + duration;
    sourceNode.playbackRate.value = rate;
    pannerNode.pan.value = pan;

    sourceNode.connect(pannerNode);
    pannerNode.connect(audioContext.destination);
    sourceNode.start(loopStart/10, loopStart);
    return sourceNode
}
function playAudio(SOUND, PATTERN) {
  fetch(SOUND)
    .then(response => response.arrayBuffer())
    .then(arrayBuffer => audioContext.decodeAudioData(arrayBuffer))
    .then(audioBuffer => {
        for(let loop=0; loop<PATTERN.length; loop++) {
            let loopPan = (((loop+1)/(PATTERN.length+1))*2) - 1;  // split values between (-1; 1)
            PLAYING_AUDIO.push(startLoop(
                audioBuffer,
                PATTERN[loop].start,
                PATTERN[loop].duration,
                1 + loop/PATTERN[loop].rateDiv,
                loopPan
            ))
        }
    })
    .catch(e => console.error(e));
    
}


function stopAll() {
    PLAYING_AUDIO.forEach((audio) => {
        audio.stop()
    })
}

wave.playStream();

