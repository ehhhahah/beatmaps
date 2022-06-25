sound_num = -1
sounds_amount = -1
SOUNDS_DATA = {
    0: ['','sznurek do prania',''],
    1: ['', 'domofon', ''],
    2: ['', 'nalewanie wody', ''],
    3: ['', 'trzmiel', ''],
    4: ['', 'pszczola', ''],
    5: ['', 'golebie', ''],
    6: ['', 'plac centralny samochod', ''],
    7: ['', 'toczaca sie butelka', ''],
    8: ['', 'butelka spada', ''],
    9: ['', 'metalowa butelka', ''],
    10: ['','butelka sie toczy (wyciete)',''],
    11: ['', 'jerzyki', ''],
    12: ['', 'gwizdanie', '']
}

# class="puzzle pieceX" onclick="playSound('nowa-huta/', X)"

color_match = 'style="fill:#'
map_file_str = ""
credits_file= ""
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
            if sound_num == -1: sound_num += 1
            elif sound_num <= sounds_amount:
                line = line.replace(
                    '<g',
                    f"""<g class="puzzle piece{sound_num}" onclick="playSound('nowa-huta/', {sound_num})" """
                    )
                sound_num += 1

        # add authorship tag
        if '</g>' in line and get_sound_info(sound_num-1):
            line = line.replace('</g>', f'<title>{get_sound_info(sound_num-1)}</title></g>')
        map_file_str += line

print(f"Generated {sound_num} pieces")

with open('nowa-huta/maps/helpers/new_map_parsed.svg', 'w') as f:
    f.write(map_file_str)

def generate_credits_double_row(sound_id):
    return f"""
<tr>
    <td>{sound_id} ↑</td>
    <td>{SOUNDS_DATA[sound_id][0]}</td>
    <td>{SOUNDS_DATA[sound_id][1]}</td>
    <td><audio controls><source src="https://beatmaps.pages.dev/nowa-huta/sounds/{sound_id}.wav"></audio></td>
</tr>
<tr>
    <td>{sound_id} ↓</td>
    <td>{SOUNDS_DATA[sound_id][0]}</td>
    <td>{SOUNDS_DATA[sound_id][2]}</td>
    <td><audio controls><source src="https://beatmaps.pages.dev/nowa-huta/sounds/{sound_id}_mod.wav"></audio></td>
</tr>"""

def generate_credits_double_empty_row(sound_id):
    return f"""
<tr>
    <td>{sound_id} ↑</td>
    <td></td>
    <td></td>
    <td><audio controls><source src="https://beatmaps.pages.dev/nowa-huta/sounds/{sound_id}.wav"></audio></td>
</tr>
<tr>
    <td>{sound_id} ↓</td>
    <td></td>
    <td></td>
    <td><audio controls><source src="https://beatmaps.pages.dev/nowa-huta/sounds/{sound_id}_mod.wav"></audio></td>
</tr>"""

for credit_num in range(sound_num):
    if credit_num in SOUNDS_DATA:
        credits_file += generate_credits_double_row(credit_num)
    else:
        credits_file += generate_credits_double_empty_row(credit_num)
    credit_num += 1

with open('nowa-huta/maps/helpers/credits_table.html', 'w') as f:
    f.write(credits_file)

