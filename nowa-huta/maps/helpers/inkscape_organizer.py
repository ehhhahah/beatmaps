sound_num = 1
# all_sounds = 11  # counting from zero

color_match = 'style="fill:#'
new_file_str = ""
MAIN_COLOR = "#ff0000"

with open('nowa-huta/maps/mapa_inkscaped_manual_cut.svg') as map_file:
    for line in map_file:
        if "<g" in line:
            if sound_num == 1: 
                sound_num += 1
                new_file_str += line
                continue

            line = line.replace(
                '<g',
                f"""<g class="puzzle piece{sound_num}" onclick="playSound('nowa-huta/', {sound_num})" """
                )
            sound_num += 1
        else:
            line = line.replace("display:inline;fill:none", f"display:inline;fill:{MAIN_COLOR}")
        new_file_str += line

print(f"Generated {sound_num} pieces")

with open('nowa-huta/maps/helpers/new_map_parsed.svg', 'w') as f:
    f.write(new_file_str)
