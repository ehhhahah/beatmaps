let ALL_AUDIOS = new Array(2)

function hideShowClassElement(className) {
    let currState = document.getElementsByClassName(`piece${className}`)[0].classList.toggle(`piece-active`);
    const elements = document.getElementsByClassName(className);

    for (let i=0; i<elements.length; i++) {
        elements[i].style.display = currState ? "block" : "none"
        elements[i].popover({
            title: "Title",
            content: "Content",
            container: 'body'
        });
    }
}

function getVerticalScrollPercentage( elm ){
    var p = elm.parentNode
    return (elm.scrollTop || p.scrollTop) / (p.scrollHeight - p.clientHeight )
  }

function checkAudioTypes(audioArray) {
    for (let i=0; i<audioArray.length; i++) {
        if (!typeof audioArray[i] === "audio") {
            return false
        }
    }
    return true
}

function setModAudioVolume(scrollSize) {
    ALL_AUDIOS.forEach(audioContainer => {
        audioContainer["audio"][0].volume = scrollSize;
        audioContainer["audio"][1].volume = 1 - scrollSize;
    });
}

function playSound(soundId) {
    const soundIndex = soundId - 1;
    console.log(ALL_AUDIOS)
    if (!ALL_AUDIOS[soundIndex]) {
        ALL_AUDIOS[soundIndex] = {
            "id": soundIndex,
            "audio": [
                new Audio(src="sounds/" + soundIndex + ".wav"),
                new Audio(src="sounds/" + soundIndex + "_mod.wav")
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
            audioObj.play()
            audioObj.loop = true
        })
        ALL_AUDIOS[soundIndex]["is_playing"] = true
    }

    document.getElementsByClassName(`piece${soundId}`)[0].classList.toggle(`piece-active`)
}

function getScrollRGBBlueToRed() {
    return `rgb(${255 - parseInt(getVerticalScrollPercentage(document.body) * 255)}, 0, ${parseInt(getVerticalScrollPercentage(document.body) * 255)})`
}

window.addEventListener('scroll', function () {
    // console.log(getVerticalScrollPercentage(document.body))
    setModAudioVolume(getVerticalScrollPercentage(document.body))
    // console.log("#0000ff" + Math.floor(getVerticalScrollPercentage(document.body) * 100).toString(16))
    // document.body.style.backgroundColor = "#0000ff" + Math.floor(getVerticalScrollPercentage(document.body) * 100).toString(16);
    document.getElementsByClassName('svgContainer')[0].style.borderColor = getScrollRGBBlueToRed()
    document.body.style.background = `linear-gradient(rgb(255, 255, 255), ${getScrollRGBBlueToRed()});`
  });
  