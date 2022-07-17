let ALL_AUDIOS = new Array(2)
let ZOOM_POSITION = 0  //0-1 range
let map = document.getElementById("svgmap");

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

function setModAudioVolumeByZoom() {
    ALL_AUDIOS.forEach(audioContainer => {
        audioContainer["audio"][0].volume = 1 - ZOOM_POSITION;
        audioContainer["audio"][1].volume = ZOOM_POSITION;
    });
}

function playSound(projectPath, soundId, fileFormat1=".mp3", fileFormat2=".mp3") {
    // projectPath = ''
    const soundIndex = soundId;
    console.log(ALL_AUDIOS)
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
            setModAudioVolumeByZoom()
            audioObj.loop = true
            audioObj.play()
        })
        ALL_AUDIOS[soundIndex]["is_playing"] = true
    }

    document.getElementsByClassName(`piece${soundId}`)[0].classList.toggle(`piece-active`)
}

if (!!navigator.platform.match(/iPhone|iPad|iPod/)) {
    console.log("IPHONE")
    document.getElementsByClassName("slider")[0].addEventListener(
        "touchend",
        (touchEvent) => {
            var element = touchEvent.srcElement;
            if (element.min && element.max && touchEvent.changedTouches && touchEvent.changedTouches.length > 0) {
                const max = Number(element.max);
                const min = Number(element.min);
                let step = 1;
                if (element.step) {
                    step = Number(element.step);
                }
                //Calculate the complete range of the slider.
                const range = max - min;
    
                const boundingClientRect = element.getBoundingClientRect();
                const touch = touchEvent.changedTouches[0];
    
                //Calculate the slider value
                const sliderValue = (touch.pageX - boundingClientRect.left) / (boundingClientRect.right - boundingClientRect.left) * range + min;
    
                //Find the closest valid slider value in respect of the step size
                for (let i = min; i < max; i += step) {
                    if (i >= sliderValue) {
                        const previousValue = i - step;
                        const previousDifference = sliderValue - previousValue;
                        const currentDifference = i - sliderValue;
                        if (previousDifference > currentDifference) {
                            //The sliderValue is closer to the previous value than the current value.
                            element.value = previousValue.toString();
                        } else {
                            element.value = i.toString();
                        }
    
                        //Trigger the change event.
                        element.dispatchEvent(new Event("change"));
                        break;
                    }
                }
            }
        },
        {
            passive: true
        }
    );
}


function slide(slideInput) {
    // SVGTransformList of the element that has been clicked on
    const tfmList = map.transform.baseVal;

    // Create a separate transform object for each transform
    const scale = map.createSVGTransform();
    scale.setScale(slideInput/100, slideInput/100);

    ZOOM_POSITION = 1 - ((slideInput - 25) / 200)
    console.log(ZOOM_POSITION)
    document.getElementById("debug").innerText = ZOOM_POSITION

    // apply the transformations by appending the SVGTransform objects to the SVGTransformList associated with the element
    tfmList.clear()
    tfmList.appendItem(scale);

    setModAudioVolumeByZoom()
}

// https://docs.google.com/presentation/d/1RPXhoVShcwOZsAoITz_CTd9_Gegd3UH2HjLFb7IyGiA/edit#slide=id.gc6f59039d_0_0
