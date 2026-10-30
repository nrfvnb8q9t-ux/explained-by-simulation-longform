# Scene templates (73)


## Space templates

### `accretion_disk`
A feeding black hole up close, as a 4-beat storyboard: a white-hot accretion disk whirls round the
    shadow (Doppler beaming makes the side coming towards us brighter and bluer, and gravity bends the far side
    of the disk up over the top), with a thin photon ring; the relativistic jets blast out of the poles; streams
    of gas spiral in from outside; then a bright clump falls through the inner disk and the payoff hits: an
    X-ray flare, a wave through the disk and surging jets. HUD counts the clump's speed as a fraction of light
    speed and the brightness.
    params: jets_at (word the jets surge on), stream_at (word the gas streams fall in), flare_at (word the clump
    falls in and flares, the payoff), title (slam on the flare, default "X-RAY FLARE", "" for none),
    size (shadow radius, default 95), palette (gold|ice|pink|ember), tilt (0.18-0.35), color, hud

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

### `doppler_shift`
The Doppler effect: a source sends out wave rings; once it moves they bunch up ahead and stretch out behind.
    Two spectrum bars (ahead and behind) show the received light shifting blue and red, with shifted absorption
    lines (or, for sound, the pitch rising and falling). The payoff: the speed goes extreme, the rings pile into a
    wall ahead and the colours slide right off the visible spectrum (sound: it breaks the sound barrier, a Mach cone).
    params: mode (light|sound), move_at (word it starts moving), fast_at (word it speeds up), extreme_at (word it
    goes extreme, the payoff), speed (first speed as a fraction of the wave speed, default 0.3), fast_speed (0.6),
    top_speed (0.9 for light, 1.4 for sound), payoff (slam text, default 'BLUESHIFT' / 'SONIC BOOM', '' for none), color

### `eclipse`
A body slides in front of a star, the light dims and the corona flares out around it.
    params: star (sun|red_giant), blocker (moon|planet kind), at (word of totality), camera

### `explosion`
A star or planet blows apart: building glow, blinding flash, rings, debris and an expanding nebula.
    params: kind (sun|red_giant|planet kind), at (word it explodes on), color (accent), size (default 150), camera

### `flyby`
The camera races past a body at high speed: streaking stars and speed lines.
    params: kind (body), direction (left|right), speed_text (e.g. '30 km/s', shown as a counter), size, camera ignored

### `free_fall`
An object dropped from the edge of space falls through the atmosphere's layers (a real drag simulation): it
    speeds up in the thin air, air streaks and a shock cone grow, its nose glows hot at max speed, then the thickening
    air slows it to terminal velocity, shown as a plateau on a live speed-vs-time graph. Earth's curved horizon flattens
    as it drops. HUD: altitude, speed, Mach, nose temperature, the current layer, and a scrolling altitude ruler.
    params: release_at (word it's let go on), peak_at (word it hits max speed), terminal_at (word it settles to
    terminal velocity, the payoff), from_km (drop height, default 100), object (capsule|rock), terminal (sea-level
    terminal speed m/s, default 90), payoff (slam text, default 'TERMINAL VELOCITY', '' for none), color

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

### `magnetosphere`
A planet's magnetic shield at work: solar-wind particles stream in from the Sun on the left and are
    deflected around the planet's field lines, as a storyboard: the wind streams past the dipole field; the bow
    shock lights up where the wind piles up and heats (magnetotail stretched behind); particles funnel down
    the field lines into the poles and auroras flare. Optional 4th beat (collapse_at or collapse: true): the
    field collapses, the wind slams into the surface and strips the atmosphere away into space.
    params: shock_at (word the bow shock lights up), aurora_at (word the auroras flare), collapse_at (word the
    field dies, optional), collapse (true to include the collapse without a word), kind (planet, default
    earth), title (slam on the last beat, optional), size (planet radius, default 82), color, hud

### `newtons_cannon`
Newton's cannon: a cannon on a mountain fires faster and faster. The first two shots arc down and land
    ('falls back'), the third falls all the way round without hitting the ground ('orbit'), the last flies off for
    good ('escape'). Trajectories are traced and stay on screen; a HUD counts the launch speed against the orbit and
    escape speeds, and the camera pulls out from the mountain to the whole planet.
    params: planet (body kind, default earth), shot1_at, shot2_at (words the two falling shots fire on),
    orbit_at (word the orbit shot fires on), escape_at (word the escape shot fires on, the payoff),
    orbit_speed (km/s, default from the planet: earth 7.9, moon 1.7, mars 3.6...), payoff (slam text on the escape,
    default 'ESCAPE VELOCITY', '' for none), color

### `orbit_system`
A star with planets on tilted orbits. Can make the star vanish, or a planet leave its orbit.
    params: star (sun|red_giant|white_dwarf|black_hole|none), planets (count 2-8, or list of kinds),
    highlight (index of a planet to label), highlight_label, event (star_vanish|planet_leave), event_at, tilt (0.2-0.6), camera

### `orbit_topdown`
Looking down on an orbit. The orbiting body can break free and fly off in a straight line.
    params: center (sun|black_hole|earth|none), orbiter (body kind), radius (default 360), release_at (word),
    speed_label (e.g. '30 km/s'), camera ignored

### `planet_formation`
How a planet is born, as a 4-beat storyboard: a glowing dusty disk spins around a young star (jets
    firing from its poles); dust clumps into planetesimals that collide and grow; one protoplanet sweeps its
    orbit and clears a dark gap; then the camera dives onto the finished planet, glowing molten-hot.
    HUD counts the system's age, the largest body and the planet's temperature.
    params: clump_at (word dust starts clumping), gap_at (word the planet clears its gap),
    glow_at (word for the payoff: the newborn planet glows), title (slam text on the payoff, default
    "A NEW PLANET", "" for none), star (body kind at the centre, default sun), palette (ember|rose|teal|sand),
    color, hud (false hides the HUD)

### `planet_hero`
One big planet, slowly spinning, with an optional change part-way through.
    params: kind (earth, mars, moon, jupiter, ...), side (left|center|right), size (radius px, default 330),
    light (left|right|top_left|top_right|front), event (freeze|darken|burn|lights|vents|glow), event_at (word),
    labels [{text, at}], camera, background (space|deep|nebula)

### `ring_system`
A planet with glittering rings. The rings can form from debris or break apart.
    params: kind (planet), tilt (0.15-0.45), ring_color, event (form|break), event_at, camera

### `roche_breakup`
A moon spirals inside its planet's Roche limit and is torn apart, as a 4-beat storyboard: the moon
    spirals in across the dashed Roche-limit line (it flashes red); tides stretch it into an egg and glowing
    fault lines crack across it while it sheds streams of dust; it shatters into rubble; then the rubble
    smears around the orbit into a brand-new ring (inner pieces orbit faster). HUD shows distance in planet
    radii, tidal stretch and status.
    params: cross_at (word the moon crosses the Roche limit), crack_at (word the cracks appear),
    break_at (word it shatters), ring_at (word the ring forms, the payoff), kind (planet, default random
    gas/ice giant), moon (moon kind: moon|rocky|ice|mars|asteroid), title (slam on the payoff, default
    "A NEW RING", "" for none), size (planet radius, default 165), color, hud

### `size_scale`
Bodies lined up by size, the camera sweeping from smallest to largest.
    params: bodies [{kind, label, radius_km}] (2-6, any order), log (true squashes huge differences), camera ignored

### `solar_flare`
A solar flare and its CME, as a 4-beat storyboard. A close-up of the Sun's boiling granulated surface,
    sunspots and glowing magnetic loops; the main loop twists and rises under stress; it snaps (reconnection):
    a blinding flare, flare ribbons and a wave across the surface, with a plasma blob torn off; then the camera
    pulls out to a wide shot where the CME bubble balloons across space to a small planet, with distance and
    hours counting up, and hits it (its magnetic shield flares).
    params: loop_at (word the loop starts twisting), snap_at (word it snaps: the flare), cme_at (word for the
    wide shot / CME launch), arrive_at (word the CME hits the planet), planet (body kind, default earth),
    km (distance, default 150000000), hours (travel time, default 40), title (slam on the flare, default
    "SOLAR FLARE", "" for none), hit_title (slam on arrival, default "DIRECT HIT", "" for none), color, hud

### `spacetime_grid`
Spacetime as a rubber sheet, in 3D: a star sits in a dip in a glowing grid. A small world rolls in and
    settles into orbit by following the curve; then the star gains mass and the dip deepens (the orbit tightens);
    the payoff: it collapses into a black hole and the middle of the grid funnels down into a bottomless throat,
    while the orbit far away doesn't change. A HUD tracks mass, radius and escape speed (which hits light speed).
    params: orbit_at (word the small world rolls in on), grow_at (word the star starts gaining mass),
    collapse_at (word it collapses, the payoff), mass (final mass in Suns, default 20), orbiter (body kind, default
    moon), payoff (slam text, default 'BLACK HOLE', '' for none), color

### `star_lifecycle`
A star changing through stages (e.g. Sun to red giant to white dwarf), each named as it happens.
    params: stages [{kind (sun|red_giant|white_dwarf|neutron_star|black_hole), name, size, at}], camera

### `surface_view`
Standing on a world's surface, looking at the sky: a body rising or hanging huge above the horizon.
    params: sky (day|sunset|night|alien), ground (rocky|ice|desert|grass|lava), sky_body (body kind),
    sky_body_size (radius, default 220), rise (true animates it rising), camera ignored

### `tidal_lock`
Why a moon ends up showing one face to its planet, as a 4-beat storyboard seen from above: the moon
    orbits and spins fast, a marker arrow on it sweeping round; the planet's gravity raises a tidal bulge on it,
    dragged ahead of the planet-moon line by the spin, and the pull on that bulge brakes the spin; the spin
    slows over millions of years (counter); then it locks, the marker points at the planet all the way round
    (ghost moons show it) and "TIDALLY LOCKED" slams in. HUD shows spins per orbit, bulge lag and time.
    params: bulge_at (word the tidal bulge appears), slow_at (word the spin starts slowing), lock_at (word it
    locks, the payoff), kind (planet, default earth), moon (moon kind, default moon), years (millions of
    years the spin-down takes, default 50), spin_ratio (spins per orbit at the start, default 4),
    title (slam on the lock, default "TIDALLY LOCKED", "" for none), color, hud

### `tides`
Why there are two tides a day, seen from above the North Pole: the oceans bulge towards the Moon and away from
    it, the Moon orbits and the bulges follow while Earth spins underneath (a marked coast sweeps through high and low
    tide on a gauge). A faint field of arrows shows the Moon's stretching (tidal) pull all around. Gravity arrows show
    the near side pulled hardest and the far side least; then the differences, which stretch the ocean both ways.
    Payoff: the Moon moves much closer and the bulges balloon (tides grow with 1/distance cubed).
    params: arrows_at (word the gravity arrows appear), stretch_at (word they turn into the stretching
    'difference' arrows), closer_at (word the Moon moves closer, the payoff), closer (new distance as a fraction,
    default 0.65), payoff (slam text, default computed like '3.6x HIGHER TIDES', '' for none), color

### `time_dilation`
Two clocks side by side: one far away, one near a black hole (or moving close to light speed). They start in
    step; as the second one goes deeper (or faster) its hands and digital counter fall behind, its signal rings get
    stretched apart and reddened, and its 'time rate' drops; at the extreme it almost freezes. Payoff: the gap between
    the two clocks slams onto the screen.
    params: mode (gravity|speed), slow_at (word clock B starts slowing), extreme_at (word it gets extreme: at the
    horizon / 99.5% of light speed), payoff_at (word the time difference slams in), unit (years|days|hours|minutes,
    default years), per_second (clock A's units per second of screen time, default 1), a_label, b_label,
    payoff (slam text, default computed like '9.4 YEARS APART', '' for none), color

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

### `dashboard`
Mission-control status board for a planet: a spinning planet in a rotating targeting reticle, with four
    live panels flying in around it (a needle gauge, a scrolling sparkline, a rolling counter and a segmented
    ring), wired to the planet. Values tick live. Escalation: one panel starts flashing WARNING; payoff on
    critical_at: that panel's value spikes, it turns red with hazard stripes, the planet gets a red halo,
    the screen shakes and CRITICAL slams in.
    params: title, kind (planet, default earth), panels [{kind (gauge|sparkline|counter|ring), label, value,
    max (gauge/ring), unit, at (word it appears on)}] (exactly 4 look best), critical (index 0-3 of the panel
    that fails), critical_value (what its value spikes or drops to), critical_at (word), slam (default 'CRITICAL'),
    color, background

### `gauge`
A speedometer-style dial whose needle swings up to a value (speed, pressure, force...).
    params: value, max, unit, caption, at, color, background

### `leaderboard`
A live, broadcast-style leaderboard: ranked glass rows (planet/icon, name, glowing value bar, counting
    number) slide in one by one, each new entry entering at the bottom and climbing past the others as the
    board re-sorts. A gold crown sits on #1. Payoff: the LAST row is the surprise, it hesitates at the bottom,
    then rockets to #1 with a flash and shake, the crown jumps to it and every other bar collapses to show how
    much bigger it is. List rows in the order they're mentioned.
    params: title, rows [{name, value (number), kind (body kind or bullet|jet|iss|rocket|probe|light, optional),
    at (word it appears on)}] (3-7, last = the surprise), unit (e.g. 'km'), slam (payoff text, default 'NEW #1'),
    sort (high = biggest is #1, default; low = smallest is #1, e.g. shortest day), log (true: log-scaled bars),
    color, background (grid|hex|space|nebula)

### `percent_ring`
A ring that fills up to a percentage, with the number in the middle (e.g. '99.8%' of the solar system's mass).
    params: percent, caption, at, color, background

### `pictogram`
A ratio you can feel ('1 in 10,000'). Starts close up on a few big icons (people, planets, stars or
    dots) popping in around one, which lights up in the accent colour and pulses with a tag. Then the camera
    pulls back and back as thousands more icons pop in at the edges and a counter climbs, until the whole grid
    is revealed, the highlighted few glow and the caption slams in. Up to 40,000 icons are drawn; above that
    each icon stands for several (shown on screen).
    params: total (whole group, e.g. 10000), highlight (how many are special, e.g. 1), icon (person|planet|star|dot),
    caption (payoff text, default '1 in 10,000'), label (tag on the highlighted icon, e.g. 'you'),
    highlight_at (word the special one lights up), zoom_at (word the pull-back starts), reveal_at (word the
    whole grid is shown), title, unit (what an icon is, e.g. 'people'), color, background

### `rank_card`
A ranked-list entry: a huge '#3', the item's name, a spinning body and 1-3 quick facts.
    params: rank, name, kind (body to show, or none), facts [text] (0-3), color, background

### `spectrum`
The electromagnetic spectrum as a HUD instrument: a band strip from radio to gamma with its true
    log-wavelength scale, a glowing wave above it that gets shorter and shorter left to right, photons riding
    it, and energy arrows. A scanning marker sweeps back and forth reading out the wavelength, then locks onto
    the band being discussed; the others dim, the camera zooms right into that band (visible light turns into a
    rainbow, and you see how thin it really is) and the band name slams in with a label card.
    params: band (radio|microwave|infrared|visible|ultraviolet|xray|gamma), label (one line about it),
    at (word the marker locks on), label_at (word the label appears, optional), title, color, background

### `speed_race`
A drag race of speeds on glowing lanes: start lights, GO, and everything launches with motion streaks.
    Distances are honest (each racer's position is its speed x time), so the camera keeps zooming out to track
    the leader: slow racers fall back to the start line while faster ones scream in from off-screen, a distance
    ruler morphs and a TRACKING readout names who the camera follows. Payoff: the camera finally locks onto the
    fastest, everything else collapses into a pile at the start, and the 'N x FASTER' ratio slams in.
    params: racers [{name, speed (number, same unit for all), unit_text (label, e.g. '7.7 km/s'),
    icon (bullet|jet|iss|rocket|probe|light|sound|dot or a body kind, optional)}] (2-6, any order),
    unit (speed unit, default 'km/s', used for the ruler), go_at (word the race starts on),
    payoff_at (word the fastest takes over), slam (payoff text), title, color, background

### `stat_grid`
2-6 fact tiles popping in one at a time, each a big number with a label. Great for "by the numbers" moments.
    Keep each value SHORT: a number or 1-3 words ("8 min", "4x", "-73°C"). Long values wrap and lose impact.
    params: title, stats [{value (text), label, at}], color, background

### `thermometer`
A thermometer whose level rises or falls to a temperature, glowing hot red or icy blue.
    params: from_c, to_c (degrees Celsius), range [lo, hi], caption, at, background

### `timeline_log`
Deep time on a logarithmic axis (each step is 10x longer). Event pins drop onto the axis one at a time,
    each with a card ('Light from the Sun - 8.3 minutes'); whenever the next event is too far away to fit, the
    camera slides and zooms out by whole decades, older events squash to the left and the tick labels morph
    from seconds to hours to years to billions of years. Payoff: the last, biggest event lands with a flash
    and its duration slams in. List events in the order they're mentioned.
    params: events [{label, seconds (duration or time ago, in seconds), at (word it drops on)}] (2-7),
    title, slam (payoff text, default the last event's duration), color, background


## Cinematic templates

### `case_file`
A mystery dossier on a dark wooden desk under a warm lamp: a case file with a polaroid of the subject (a
    procedurally drawn planet, star or black hole), lines typing out one by one, a redaction bar that wipes off to
    reveal the key line (with red marker circling the photo), then a rubber stamp SLAMS down: UNSOLVED, CONFIRMED,
    DEBUNKED... Use for "the case of...", real mysteries, myth-busting and verdicts.
    params: title (case name), subject_kind (body in the photo: earth, mars, ice, black_hole, red_giant...),
    lines [{text, at}] (2-5 short typed lines; at = word each types on), redact (index of the hidden line,
    default the last), redact_at (word the bar wipes off), stamp (UNSOLVED|CONFIRMED|DEBUNKED|any short word),
    stamp_at (word it slams on), note (handwritten scribble, default "?!"), case_no, color

### `chain_reaction`
A cause-and-effect chain told as one tracking shot: glowing event nodes joined by arrows. Each node lights up
    on its word as an energy pulse races down the arrow into it, the camera tracking along the chain; the last node
    detonates (flash, shockwave, shattered ring) and the camera pulls back to show the whole chain lit.
    Great for "and then... and then..." consequences (e.g. Sun vanishes -> orbit straightens -> darkness -> freeze).
    params: steps [{text, at, kind}] (2-6 short events; at = narration word it lights on; kind = optional body
    drawn in the node, otherwise an icon is chosen from the text), title (small HUD heading, default "CHAIN REACTION"),
    payoff (optional slam text on the final detonation), layout (line|zigzag|arc), color

### `hologram_scan`
A sci-fi hologram: a wireframe body being scanned, with a HUD of readouts appearing line by line.
    params: kind (body), readouts [{label, value, at}] (1-5), color

### `kinetic_text`
Kinetic typography: a key line's words punching onto the screen one by one, on the beat.
    params: words [{text, at, color}] (2-8 short words/phrases), background (space|black|nebula), color

### `mission_control`
A full mission-control console: panels boot up, a trajectory map shows the craft gliding from its home planet
    towards the target, telemetry graphs scroll, readouts count up on their words and status lights flip green ->
    amber as a countdown runs... then ALERT: everything goes red, the screen shakes, the graphs spike and the craft
    veers off its planned path. Use for missions, probes, "what would NASA see", near misses and emergencies.
    params: craft (name, e.g. "Voyager 1"), origin_kind (default earth), target_kind (body the craft heads for),
    readouts [{label, value, at}] (2-5; numbers in value count up), alert_text (default "ALERT"),
    alert_at (word the alarm hits on), status (small line under the alert, optional), color

### `particle_gas`
Molecules bouncing in a box. Their speed shows temperature: they can slow to a crawl (freezing) or go wild (heating).
    params: count (40-200), temp (0-1 start), to_temp (0-1), change_at (word), label, color

### `question_card`
A big mystery question with a pulsing question mark, for opening a 'real mystery' section.
    params: question (one short line), color

### `radar_scan`
A radar sweep picking up objects one by one (asteroids, signals, planets), each tagged as it's found.
    params: targets [{label, at}] (1-5), color

### `reveal`
The shock drop. Darkness and a heartbeat glow while the narration builds, then on the key word a blinding
    hit and the reveal slams in: a body or a huge number, with a shockwave, debris and a punchline.
    Use it for the 2-4 most jaw-dropping facts in a video, with the scene's "drop" on the same word.
    params: at (the reveal word, required), kind (body to reveal, e.g. black_hole, red_giant, earth),
    number (text instead of a body, e.g. "1,300,000x"), title (punchline, 1-4 words), sub (one line), color, size

### `scale_dive`
One continuous 'powers of ten' zoom through nested scales from the human world outward (person -> city ->
    country -> Earth -> the Moon's orbit -> Earth's orbit), or inward with direction "in". Each scale is drawn
    procedurally (a person, city blocks and lights, a coastline, planets, orbit rings, a galaxy), the zoom has real
    motion blur, and a HUD shows the name, a size bar with the real size and a ladder of all the levels.
    Differs from zoom_scale (planet -> galaxy): this one starts at human size and shows sizes.
    params: levels [{label, size_text, at, kind}] (2-7, smallest first; at = word the zoom arrives on; kind
    optional: person|city|country|orbit|solar|galaxy|ring|any body kind, otherwise guessed from label),
    direction (out|in), color

### `split_compare`
Before and after, side by side: the screen splits with a sliding divider (e.g. Earth now vs Earth frozen).
    params: left {kind, label}, right {kind, label}, at (word the divider sweeps in on), color

### `timeline_journey`
A flight along a glowing timeline: the camera races down a neon time-line over a perspective grid while a big
    counter runs (seconds, years, millions of years). Milestone panels with icons pop up as each is reached, the time
    scale visibly accelerates (a 'time warp' readout shows units per second), and the last milestone lands with a flash.
    Use for "8 minutes later... a year later... a million years later" stories, or the history of something.
    params: events [{label, time_text, at, value, kind}] (2-6; at = word its panel pops on; value = number in `unit`
    for the counter, read from time_text if missing; kind = optional body icon), unit (e.g. "years", "seconds",
    "years after the Big Bang"; counter caption), payoff (optional slam text on the last event), color

### `title_card`
A chapter title: big text slamming in over a glowing nebula and drifting particles, then a slow push-in
    with beat-pulsing glow, light sweeps and the chapter's planet rising behind it, so it never sits still.
    params: title, number (chapter number, optional), sub, color, style (slam|type|glitch), kind (body behind it, optional)

### `versus_showdown`
A fight-night face-off between two bodies: split-colour arena, a lightning 'VS' slam, then round by round a
    stat appears and both bars fill and compare (the round's winner flares and scores a point). On the winner beat
    the loser's bars drain and it dims, and the winner gets a spotlight, a halo and a WINNER slam.
    Use for "Earth vs Mars", "Jupiter vs the Sun", "which would win" comparisons with 2-5 numbers.
    params: left {name, kind}, right {name, kind}, rounds [{stat, left, right, left_text, right_text, better, at}]
    (2-5; left/right are numbers for the bars, *_text how they're shown, better = "lower" if smaller wins;
    at = word the round appears on), winner (left|right, default whoever won most rounds), vs_at, winner_at, color

### `warp`
A hyperspace jump: stars stretch into streaks rushing past, then snap back as we arrive somewhere new.
    params: destination (text shown on arrival), arrive_at (word), color, kind (body we arrive at, optional)

### `waves`
Glowing waves travelling across the screen (light, sound, gravitational waves), which can change
    frequency or size part-way through.
    params: label, count (1-3 waves), wavelength (px, default 260), to_wavelength, amplitude, to_amplitude, change_at, color

