function playSound(sound) {
    switch(sound) {
        case 1:
            new Audio(src='samples/325647__shadydave__expressions-of-the-mind-piano-loop.wav').play();
            break;
        case 2:
            new Audio(src='samples/624436__monosfera__swimming-pool-kids.wav').play();
            break;
        case 3:
            new Audio(src='samples/624438__monosfera__fxdrone-001.wav').play();
            break;
    }
}