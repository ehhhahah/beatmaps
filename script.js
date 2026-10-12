// --- SEKCJA WEB AUDIO API (BEZPRZERWOWE PĘTLE Z FALLBACKIEM) ---
const WebAudioContext = window.AudioContext || window.webkitAudioContext;
let audioCtx;

class SeamlessAudio {
    constructor(src) {
        this.src = src;
        // Tworzymy Audio, ale NIE podajemy mu jeszcze ścieżki (src). 
        // Zapobiega to wysyłaniu konfliktowych zapytań Range przez przeglądarkę.
        // 416 (Requested Range Not Satisfiable)
        this.audioElement = new Audio(); 
        this.useWebAudio = !!WebAudioContext;
        this.gainNode = null;
        this.sourceNode = null;
        this.audioBuffer = null;
        this._volume = 1;
    }

    async play() {
        if (this.useWebAudio) {
            try {
                // Inicjalizacja kontekstu po pierwszej interakcji użytkownika
                if (!audioCtx) {
                    audioCtx = new WebAudioContext();
                }
                if (audioCtx.state === 'suspended') {
                    await audioCtx.resume();
                }                
                
                // Pobieranie i dekodowanie pliku (tylko raz)
                if (!this.audioBuffer) {
                    const response = await fetch(this.src);
                    if (!response.ok) throw new Error("Błąd pobierania pliku: " + this.src + response.status);
                    const arrayBuffer = await response.arrayBuffer();
                    this.audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
                }
                
                // Konfiguracja idealnej pętli
                this.sourceNode = audioCtx.createBufferSource();
                this.sourceNode.buffer = this.audioBuffer;
                this.sourceNode.loop = true;
                
                // Konfiguracja kontroli głośności
                this.gainNode = audioCtx.createGain();
                this.gainNode.gain.value = this._volume;
                
                this.sourceNode.connect(this.gainNode);
                this.gainNode.connect(audioCtx.destination);
                
                this.sourceNode.start(0);
            } catch (e) {
                console.warn("Używam standardowego tagu <audio>. Powód:", e.message);
                this.useWebAudio = false;
                
                // Przypisujemy src do fallbacku dopiero, gdy Web Audio API zawiedzie
                if (!this.audioElement.src) {
                    this.audioElement.src = this.src;
                }
                
                this.audioElement.loop = true;
                this.audioElement.volume = this._volume;
                this.audioElement.play();
            }
        } else {
            if (!this.audioElement.src) {
                this.audioElement.src = this.src;
            }
            this.audioElement.loop = true;
            this.audioElement.volume = this._volume;
            this.audioElement.play();
        }
    }

    pause() {
        if (this.useWebAudio) {
            if (this.sourceNode) {
                try { this.sourceNode.stop(); } catch(e) {}
                this.sourceNode.disconnect();
                this.sourceNode = null;
            }
        } else {
            this.audioElement.pause();
        }
    }

    set volume(val) {
        this._volume = val;
        // Płynna zmiana głośności w Web Audio API
        if (this.useWebAudio && this.gainNode) {
            this.gainNode.gain.value = val;
        }
        // Aktualizacja fallbacka
        this.audioElement.volume = val;
    }

    get volume() {
        return this._volume;
    }
}
// --- KONIEC SEKCJI WEB AUDIO API ---


let ALL_AUDIOS = new Array(2)
let ZOOM_POSITION = 0  //0-1 range
let map = document.getElementById("svgmap");
if (typeof RangeTouch !== 'undefined' && document.querySelector('input[type="range"]')) {
    new RangeTouch('input[type="range"]');
}

function hideShowClassElement(className) {
    let currState = document.getElementsByClassName(`piece${className}`)[0].classList.toggle(`piece-active`);
    const elements = document.getElementsByClassName(className);

    for (let i=0; i<elements.length; i++) {
        elements[i].style.display = currState ? "block" : "none"
    }
}

function checkAudioTypes(audioArray) {
    for (let i=0; i<audioArray.length; i++) {
        if (!audioArray[i]) {
            return false
        }
    }
    return true
}

function setModAudioVolumeByZoom(isSlide=false) {
    ALL_AUDIOS.forEach(audioContainer => {
        let iosDebug = false;
        audioContainer["audio"][0].volume = 1 - ZOOM_POSITION;
        audioContainer["audio"][1].volume = ZOOM_POSITION;

        if (audioContainer["audio"][0].volume !== 1 - ZOOM_POSITION && isSlide && iosDebug) {
            audioContainer["audio"][0].pause()
            audioContainer["audio"][0].volume = 1 - ZOOM_POSITION
            audioContainer["audio"][0].play()
        }

        if (audioContainer["audio"][1].volume !== ZOOM_POSITION && isSlide && iosDebug) {
            audioContainer["audio"][1].pause()
            audioContainer["audio"][1].volume = ZOOM_POSITION
            audioContainer["audio"][1].play()
        }
    });
}

function playSound(projectPath, soundId, fileFormat1=".mp3", fileFormat2=".mp3") {
    const soundIndex = soundId;
    console.log(ALL_AUDIOS)
    if (!ALL_AUDIOS[soundIndex]) {
        ALL_AUDIOS[soundIndex] = {
            "id": soundIndex,
            "audio": [
                // Użycie seamless klasy zamiast standardowego new Audio()
                new SeamlessAudio(projectPath + "sounds/" + soundIndex + fileFormat1),
                new SeamlessAudio(projectPath + "sounds/" + soundIndex + "_mod" + fileFormat2)
            ],
            "is_playing": false,
        }
    }

    if (!checkAudioTypes(ALL_AUDIOS[soundIndex]["audio"])) {
        console.log("NOT LOADED YET")
        return
    }

    if (ALL_AUDIOS[soundIndex]["is_playing"]) {
        ALL_AUDIOS[soundIndex]["audio"].forEach(audioObj => {
            audioObj.pause()
        })
        ALL_AUDIOS[soundIndex]["is_playing"] = false
    }

    else {
        ALL_AUDIOS[soundIndex]["audio"].forEach(audioObj => {
            setModAudioVolumeByZoom()
            // flaga loop jest ustawiana i obsługiwana wewnętrznie w SeamlessAudio
            audioObj.play()
        })
        ALL_AUDIOS[soundIndex]["is_playing"] = true
    }

    document.getElementsByClassName(`piece${soundId}`)[0].classList.toggle(`piece-active`)
}

function slide(slideInput) {
    // SVGTransformList of the element that has been clicked on
    const tfmList = map.transform.baseVal;

    // Create a separate transform object for each transform
    const scale = map.createSVGTransform();
    scale.setScale(slideInput/100, slideInput/100);

    ZOOM_POSITION = 1 - ((slideInput - 25) / 200)
    console.log(ZOOM_POSITION)
    document.getElementById("debug").innerText += " " + ZOOM_POSITION

    // apply the transformations by appending the SVGTransform objects to the SVGTransformList associated with the element
    tfmList.clear()
    tfmList.appendItem(scale);

    setModAudioVolumeByZoom(true)
}