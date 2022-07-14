const { pan, zoom, getScale, setScale, resetScale } = svgPanZoomContainer;

let ALL_AUDIOS = new Array(2)
let SCROLL_POSITION = 0
const ZOOM_MIN = 0.3
const ZOOM_MAX = 5

function hideShowClassElement(className) {
    let currState = document.getElementsByClassName(`piece${className}`)[0].classList.toggle(`piece-active`);
    const elements = document.getElementsByClassName(className);

    for (let i=0; i<elements.length; i++) {
        elements[i].style.display = currState ? "block" : "none"
    }
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
        audioContainer["audio"][0].volume = 1 - SCROLL_POSITION;
        audioContainer["audio"][1].volume = SCROLL_POSITION;
    });
}

function playSound(projectPath, soundId, fileFormat1=".mp3", fileFormat2=".mp3") {
    // projectPath = ''
    const soundIndex = soundId;
    // console.log(ALL_AUDIOS)
    if (!ALL_AUDIOS[soundIndex]) {
        ALL_AUDIOS[soundIndex] = {
            "id": soundIndex,
            "audio": [
                new Audio(src=projectPath + "sounds/" + soundIndex + fileFormat1),
                new Audio(src=projectPath + "sounds/" + soundIndex + "_mod" + fileFormat2)
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

function getZoomPercentage(htmlObj) {
    return (getScale(htmlObj) - ZOOM_MIN)/(ZOOM_MAX - ZOOM_MIN)
}

const container_ = document.getElementsByClassName('svgContainer')[0]

const observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (mutation) {
        console.log('scale:', getZoomPercentage(container_));
        SCROLL_POSITION = getZoomPercentage(container_)
        setModAudioVolumeByScroll()
    });
});

observer.observe(container_.firstElementChild, {
    attributes: true,
    attributeFilter: ['transform'],
});
