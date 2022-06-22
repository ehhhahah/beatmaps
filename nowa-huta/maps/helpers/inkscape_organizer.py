sound_num = 1
# all_sounds = 11  # counting from zero

color_match = 'style="fill:#'
color_main = '#ff0000'

new_file_str = ""

with open('maps/mapa_inkscaped.svg') as map_file:
    for line in map_file:
        # TODO line = line.replace('fill:#000000', "")
        if "<g" in line:
            # TODO if sound_num == 1: sound_num += 1 continue

            line = line.replace(
                '<g',
                f"""<g class="puzzle piece{sound_num}" onclick="playSound('nowa-huta/', {sound_num})" """
                )
            sound_num += 1
        new_file_str += line

print(f"Generated {sound_num} pieces")

with open('maps/helpers/new_map_parsed.svg', 'w') as f:
    f.write(new_file_str)
