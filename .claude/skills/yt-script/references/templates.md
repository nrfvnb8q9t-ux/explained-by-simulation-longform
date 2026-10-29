# Scene templates (48)


## Space templates

### `asteroid_field`
Flying through a field of tumbling rocks, with one picked out and labelled.
    params: count (20-60), highlight_label, density (0.5-2), camera ignored

### `atmosphere_escape`
A planet's air being stripped away into space in glowing streams.
    params: kind (planet), wind_from (left|right), color, at (word it starts on), camera

### `black_hole`
A black hole with a glowing accretion disk. Can pull something in and swallow it.
    params: size (shadow radius, default 110), spin (0.5-2), color (accent), consume (body kind to fall in),
    consume_at (word it gets swallowed on), camera

### `comet`
A comet swinging past a star, its glowing tail always pointing away from the star.
    params: star (sun|none), color, camera

### `cutaway`
A planet with a wedge cut out to show its layers, each labelled as it's mentioned.
    params: kind (body), layers [{name, color, depth (0-1 from the surface), at}], side (left|right), camera

### `eclipse`
A body slides in front of a star, the light dims and the corona flares out around it.
    params: star (sun|red_giant), blocker (moon|planet kind), at (word of totality), camera

### `explosion`
A star or planet blows apart: building glow, blinding flash, rings, debris and an expanding nebula.
    params: kind (sun|red_giant|planet kind), at (word it explodes on), color (accent), size (default 150), camera

### `flyby`
The camera races past a body at high speed: streaking stars and speed lines.
    params: kind (body), direction (left|right), speed_text (e.g. '30 km/s', shown as a counter), size, camera ignored

### `galaxy`
A spiral galaxy of thousands of stars, slowly turning, with an optional 'you are here' marker.
    params: arms (2-4), color, here_label (e.g. 'You are here'), here_at, tilt (0.4-1), camera

### `gravity_pull`
Two bodies tugging on each other: pulsing field lines and a stretched (tidal) bulge.
    params: a (big body kind), b (smaller body kind), distance (0.3-1, closer = stronger pull), label, camera

### `impact`
Something slams into a planet: approach trail, flash, shockwave, debris and a glowing crater.
    params: target (planet kind), impactor (asteroid|moon|comet|planet kind), at (word it hits on),
    from (left|right|top), size (impactor radius, default 40), camera

### `light_travel`
A pulse of light (or anything) crossing from one body to another, with a running timer.
    params: a, b (body kinds), a_label, b_label, distance_label ('150 million km'), seconds (real travel time,
    for the timer, e.g. 500), at (word it sets off on), color, camera

### `orbit_system`
A star with planets on tilted orbits. Can make the star vanish, or a planet leave its orbit.
    params: star (sun|red_giant|white_dwarf|black_hole|none), planets (count 2-8, or list of kinds),
    highlight (index of a planet to label), highlight_label, event (star_vanish|planet_leave), event_at, tilt (0.2-0.6), camera

### `orbit_topdown`
Looking down on an orbit. The orbiting body can break free and fly off in a straight line.
    params: center (sun|black_hole|earth|none), orbiter (body kind), radius (default 360), release_at (word),
    speed_label (e.g. '30 km/s'), camera ignored

### `planet_hero`
One big planet, slowly spinning, with an optional change part-way through.
    params: kind (earth, mars, moon, jupiter, ...), side (left|center|right), size (radius px, default 330),
    light (left|right|top_left|top_right|front), event (freeze|darken|burn|lights|vents|glow), event_at (word),
    labels [{text, at}], camera, background (space|deep|nebula)

### `ring_system`
A planet with glittering rings. The rings can form from debris or break apart.
    params: kind (planet), tilt (0.15-0.45), ring_color, event (form|break), event_at, camera

### `size_scale`
Bodies lined up by size, the camera sweeping from smallest to largest.
    params: bodies [{kind, label, radius_km}] (2-6, any order), log (true squashes huge differences), camera ignored

### `star_lifecycle`
A star changing through stages (e.g. Sun to red giant to white dwarf), each named as it happens.
    params: stages [{kind (sun|red_giant|white_dwarf|neutron_star|black_hole), name, size, at}], camera

### `surface_view`
Standing on a world's surface, looking at the sky: a body rising or hanging huge above the horizon.
    params: sky (day|sunset|night|alien), ground (rocky|ice|desert|grass|lava), sky_body (body kind),
    sky_body_size (radius, default 220), rise (true animates it rising), camera ignored

### `two_bodies`
Two bodies side by side for a comparison or 'versus', with names and an optional winner.
    params: a {kind, label, size}, b {kind, label, size}, vs (true shows a VS slam), winner (a|b),
    verdict_at (word the winner lights up on), camera

### `zoom_scale`
A 'powers of ten' zoom-out: from a planet, to its system, to the galaxy and beyond, each stage named.
    params: stages [{name, at}] (2-4 names for: planet, orbit, star neighbourhood, galaxy), kind (start body)


## Board templates

### `board_compare`
Two columns compared row by row (e.g. Earth vs Mars), with bars showing which is bigger.
    params: left, right (column headings), rows [{label, left, right (numbers), unit, at}] (1-5), board

### `board_diagram`
A hand-drawn diagram: 2-5 labelled things (circles, boxes or sketched planets) joined by labelled arrows,
    each appearing as it's mentioned.
    params: title, nodes [{label, shape (circle|box|planet|star), at}], links [{from, to, label, at}] (indexes),
    layout (row|triangle|arc), board (chalk|blueprint|dark_grid|whiteboard)

### `board_forces`
A force diagram: an object with arrows for each force (gravity, thrust, drag...), drawn on one by one.
    params: object (label), shape (circle|box|rocket), forces [{label, direction (up|down|left|right or degrees), size (0.5-2), at}], board

### `board_graph`
A hand-drawn graph: axes, then a curve sketched on, with a marked point.
    params: title, x_label, y_label, values (list of numbers), x_ticks [[frac, text]], y_ticks [[frac, text]],
    mark (index of a point to circle), mark_label, at (word the curve starts drawing on), board

### `board_notes`
Key points written on the board one by one, with the most important one circled or underlined.
    params: title, lines [{text, at}] (2-5), highlight (index to circle), doodle (arrow|circle|underline|star),
    board

### `board_orbit`
A hand-drawn orbit: a central body, an elliptical path, the orbiting body moving round it, with
    arrows for its speed and the pull towards the centre.
    params: center_label, orbiter_label, ellipse (0.4-1, 1 = circle), show_forces (true), board

### `board_sketch`
A big hand-sketched planet (or star) with features pointed out: poles, oceans, storms, layers, moons.
    params: title, body_label, features [{label, angle (degrees round the edge), at}] (1-5), hatch (true shades one side), board

### `board_steps`
A process in numbered steps joined by arrows (e.g. how a star forms), each step written as it's said.
    params: title, steps [{text, at}] (2-5), direction (across|down), board

### `board_timeline`
A timeline drawn across the board, with events ticked off in order as they're mentioned.
    params: title, events [{when ('8 min', '1 year'), label, at}] (2-7), board


## Data templates

### `bars`
Horizontal bars that grow to their values one by one, biggest highlighted. Good for rankings and comparisons.
    params: title, items [{label, value, at}] (2-8), unit, sort (true), log (true for huge ranges), color, background

### `big_number`
A huge number that counts up (or down) to its value and lands with a hit, with a caption under it.
    params: value, from (start value, default 0), unit (e.g. ' km/s'), prefix, decimals, caption, at (word the count starts on),
    count_seconds (default 1.8), color, background

### `chart`
A glowing line chart that draws itself, with an optional highlighted point and callout.
    params: title, values (numbers), x_labels [[frac, text]], y_labels [[frac, text]], y_range [lo, hi],
    zero_line, highlight (index), highlight_label, highlight_at, at (word it starts drawing on), color, background

### `countdown`
A big digital clock counting time passing (or down), e.g. '8:20' of light travel or 'Day 365'.
    params: seconds (end value, e.g. 500 for 8:20), mode (clock|days|years), down (true counts down), caption, at, color, background

### `gauge`
A speedometer-style dial whose needle swings up to a value (speed, pressure, force...).
    params: value, max, unit, caption, at, color, background

### `percent_ring`
A ring that fills up to a percentage, with the number in the middle (e.g. '99.8%' of the solar system's mass).
    params: percent, caption, at, color, background

### `rank_card`
A ranked-list entry: a huge '#3', the item's name, a spinning body and 1-3 quick facts.
    params: rank, name, kind (body to show, or none), facts [text] (0-3), color, background

### `stat_grid`
2-6 fact tiles popping in one at a time, each a big number with a label. Great for 'by the numbers' moments.
    params: title, stats [{value (text), label, at}], color, background

### `thermometer`
A thermometer whose level rises or falls to a temperature, glowing hot red or icy blue.
    params: from_c, to_c (degrees Celsius), range [lo, hi], caption, at, background


## Cinematic templates

### `hologram_scan`
A sci-fi hologram: a wireframe body being scanned, with a HUD of readouts appearing line by line.
    params: kind (body), readouts [{label, value, at}] (1-5), color

### `kinetic_text`
Kinetic typography: a key line's words punching onto the screen one by one, on the beat.
    params: words [{text, at, color}] (2-8 short words/phrases), background (space|black|nebula), color

### `particle_gas`
Molecules bouncing in a box. Their speed shows temperature: they can slow to a crawl (freezing) or go wild (heating).
    params: count (40-200), temp (0-1 start), to_temp (0-1), change_at (word), label, color

### `question_card`
A big mystery question with a pulsing question mark, for opening a 'real mystery' section.
    params: question (one short line), color

### `radar_scan`
A radar sweep picking up objects one by one (asteroids, signals, planets), each tagged as it's found.
    params: targets [{label, at}] (1-5), color

### `split_compare`
Before and after, side by side: the screen splits with a sliding divider (e.g. Earth now vs Earth frozen).
    params: left {kind, label}, right {kind, label}, at (word the divider sweeps in on), color

### `title_card`
A chapter title: big text slamming in over a glowing nebula and drifting particles.
    params: title, number (chapter number, optional), sub, color, style (slam|type|glitch)

### `warp`
A hyperspace jump: stars stretch into streaks rushing past, then snap back as we arrive somewhere new.
    params: destination (text shown on arrival), arrive_at (word), color, kind (body we arrive at, optional)

### `waves`
Glowing waves travelling across the screen (light, sound, gravitational waves), which can change
    frequency or size part-way through.
    params: label, count (1-3 waves), wavelength (px, default 260), to_wavelength, amplitude, to_amplitude, change_at, color

