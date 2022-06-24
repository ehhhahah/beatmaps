sound_num = -1
SOUNDS_DATA = {
    0: ["Wojtek", "Gruszka na wierzbie", "Sosna na lipie"],
    1: ["Asia", "ŚcieżĄ zła", "GĄŚĆŻÓŁĆŹ"],
    2: ["Asia", "ŚcieżĄ zła", "GĄŚĆŻÓŁĆŹ"]
}

color_match = 'style="fill:#'
new_file_str = ""
MAIN_COLOR = "#ff0000"

def get_sound_info(sound_id):
    return f"""
    Top sound: "{SOUNDS_DATA[sound_id][1]}"
    Bottom sound: "{SOUNDS_DATA[sound_id][2]}"

    Author: {SOUNDS_DATA[sound_id][0]}
    """ if sound_id in SOUNDS_DATA else None


with open('nowa-huta/maps/mapa_inkscaped_manual_cut.svg') as map_file:
    for line in map_file:
        # get rid of colors
        if 'style="fill:#000000"' in line:
            line = line.replace('style="fill:#000000"', '')
        if ';fill:#000000' in line:
            line = line.replace(';fill:#000000', '')
        if 'fill="#000000"' in line:
            line = line.replace('fill="#000000"', '')
        if 'stroke="none"' in line:
            line = line.replace('stroke="none"', '')

        # add sounds to groups
        if "<g" in line:
            if sound_num != -1:
                line = line.replace(
                    '<g',
                    f"""<g class="puzzle piece{sound_num}" onclick="playSound('nowa-huta/', {sound_num})" """
                    )
            sound_num += 1

        # add authorship tag
        if '</g>' in line and get_sound_info(sound_num-1):
            line = line.replace('</g>', f'<title>{get_sound_info(sound_num-1)}</title></g>')
        new_file_str += line

print(f"Generated {sound_num} pieces")

with open('nowa-huta/maps/helpers/new_map_parsed.svg', 'w') as f:
    f.write(new_file_str)
