let ALL_AUDIOS = new Array(2)
let SCROLL_POSITION = 0

function hideShowClassElement(className) {
    let currState = document.getElementsByClassName(`piece${className}`)[0].classList.toggle(`piece-active`);
    const elements = document.getElementsByClassName(className);

    for (let i=0; i<elements.length; i++) {
        elements[i].style.display = currState ? "block" : "none"
    }
}

function getVerticalScrollPercentage(elm) {
    let p = elm.parentNode
    let volume = (elm.scrollTop || p.scrollTop) / (p.scrollHeight - p.clientHeight )
    return volume > 1 ? 1 : volume 
}

function checkAudioTypes(audioArray) {
    for (let i=0; i<audioArray.length; i++) {
        if (!typeof audioArray[i] === "audio") {
            return false
        }
    }
    return true
}

function setModAudioVolumeByScroll() {
    ALL_AUDIOS.forEach(audioContainer => {
        audioContainer["audio"][0].volume = SCROLL_POSITION;
        audioContainer["audio"][1].volume = 1 - SCROLL_POSITION;
    });
}

function playSound(projectPath, soundId) {
    const soundIndex = soundId;
    console.log(ALL_AUDIOS)
    if (!ALL_AUDIOS[soundIndex]) {
        ALL_AUDIOS[soundIndex] = {
            "id": soundIndex,
            "audio": [
                new Audio(src=projectPath + "sounds/" + soundIndex + ".mp3"),
                new Audio(src=projectPath + "sounds/" + soundIndex + "_mod.wav")
            ],
            "is_playing": false,
        }
        ALL_AUDIOS[soundIndex]
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
            setModAudioVolumeByScroll()
            audioObj.loop = true
            audioObj.play()
        })
        ALL_AUDIOS[soundIndex]["is_playing"] = true
    }

    document.getElementsByClassName(`piece${soundId}`)[0].classList.toggle(`piece-active`)
}

window.addEventListener('scroll', function () {
    SCROLL_POSITION = getVerticalScrollPercentage(document.body)
    setModAudioVolumeByScroll()
});
