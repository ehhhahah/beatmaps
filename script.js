var ALL_AUDIOS = new Array(2)

function hideShowClassElement(className) {
    let currState = document.getElementsByClassName(`piece${className}`)[0].classList.toggle(`piece-active`);
    const elements  = document.getElementsByClassName(className);

    for (let i=0; i<elements.length; i++) {
        elements[i].style.display = currState ? "block" : "none"
    }
}

function playSound(soundId) {
    const soundIndex = soundId - 1;
    console.log(ALL_AUDIOS)
    if (!ALL_AUDIOS[soundIndex]) {
        ALL_AUDIOS[soundIndex] = {
            "id": soundIndex,
            "audio": new Audio(src="sounds/" + soundIndex + ".wav"),
            "is_playing": false,
        }
    }

    if (!typeof ALL_AUDIOS[soundIndex]["audio"] === "audio") {
        console.log("NOT LOADED YET")
        return
    }

    if (ALL_AUDIOS[soundIndex]["is_playing"]) {
        ALL_AUDIOS[soundIndex]["audio"].pause()
        ALL_AUDIOS[soundIndex]["is_playing"] = false
    }
    else {
        ALL_AUDIOS[soundIndex]["audio"].play()
        ALL_AUDIOS[soundIndex]["audio"].loop = true
        ALL_AUDIOS[soundIndex]["is_playing"] = true
    }

    document.getElementsByClassName(`piece${soundId}`)[0].classList.toggle(`piece-active`)
}
