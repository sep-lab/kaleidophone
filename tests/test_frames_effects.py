"""frames/effects.py: the per-pixel, stateful effects, on synthetic arrays only.

No media, no ffmpeg, nothing decoded -- every frame here is a few thousand
numbers made in code (see AGENTS.md, "Testing"). Several tests pin the lessons
the effects' docstrings are built around, so they can't quietly regress:
copies must get paler, a checkpointed effect must resume bit-identically, a
protected face must stay live, and a zero-strength effect must be a no-op.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kaleidophone.frames import effects as fx

H, W = 36, 64  # 16:9 and small -- the whole module's tests run in well under a second


def _noise(seed: int = 0, h: int = H, w: int = W) -> np.ndarray:
    return np.random.default_rng(seed).random((h, w, 3), dtype=np.float32)


def _solid(rgb, h: int = H, w: int = W) -> np.ndarray:
    return np.broadcast_to(np.asarray(rgb, np.float32), (h, w, 3)).copy()


def _luma(img: np.ndarray) -> float:
    return float((img @ np.array([0.2126, 0.7152, 0.0722], np.float32)).mean())


def _chroma(px) -> float:
    return float(np.max(px) - np.min(px))


# --- helpers: smoothstep, Keyframes, pulse, ellipse_mask ------------------


def test_smoothstep_eases_between_its_edges_for_scalars_and_arrays():
    assert fx.smoothstep(0.0, 1.0, -1.0) == 0.0
    assert fx.smoothstep(0.0, 1.0, 0.5) == 0.5
    assert fx.smoothstep(0.0, 1.0, 2.0) == 1.0
    arr = fx.smoothstep(0.0, 1.0, np.array([0.25, 0.75], np.float32))
    assert arr.dtype == np.float32  # full-frame callers stay float32
    assert arr[0] < 0.25 and arr[1] > 0.75  # an S-curve, not a line


def test_smoothstep_with_reversed_edges_falls_and_equal_edges_step():
    assert fx.smoothstep(1.0, 0.0, 0.0) == 1.0
    assert fx.smoothstep(1.0, 0.0, 1.0) == 0.0
    assert fx.smoothstep(0.5, 0.5, 0.4) == 0.0
    assert fx.smoothstep(0.5, 0.5, 0.6) == 1.0


def test_keyframes_hold_ease_and_jump():
    sched = fx.Keyframes([(20, 0.0), (0, 1.0), (10, 1.0), (10, 0.5)])  # unsorted on purpose
    assert sched(-5) == 1.0  # before the first keyframe: hold it
    assert sched(9.99) == 1.0
    assert sched(10) == 0.5  # two keyframes at one time: a jump
    assert sched(15) == pytest.approx(0.25)  # eased halfway from 0.5 to 0.0
    assert sched(30) == 0.0  # after the last: hold it


def test_keyframes_need_a_point():
    with pytest.raises(ValueError):
        fx.Keyframes([])


def test_pulse_is_one_on_the_event_and_decays_after_it():
    beats = np.array([1.0, 2.0])
    assert fx.pulse(1.0, beats) == 1.0
    assert fx.pulse(1.12, beats, tau=0.12) == pytest.approx(math.exp(-1))
    assert fx.pulse(0.5, beats) == 0.0  # nothing has happened yet
    assert fx.pulse(1.0, []) == 0.0


def test_pulse_counts_an_event_one_frame_early():
    # The frame on screen when the beat lands (up to 40 ms before it at 25 fps)
    # is the one that should carry it.
    assert fx.pulse(0.97, [1.0]) == 1.0
    assert fx.pulse(0.9, [1.0]) == 0.0


def test_ellipse_mask_is_one_inside_zero_outside_and_soft_when_feathered():
    hard = fx.ellipse_mask(H, W, (32, 18), (10, 6))
    assert hard[18, 32] == 1.0 and hard[0, 0] == 0.0
    assert set(np.unique(hard)) <= {0.0, 1.0}
    soft = fx.ellipse_mask(H, W, (32, 18), (10, 6), feather=0.3)
    assert ((soft > 0.0) & (soft < 1.0)).any()
    assert not fx.ellipse_mask(H, W, (32, 18), (0, 6)).any()


# --- MemoryCanvas ---------------------------------------------------------


def test_memory_canvas_blocks_are_48x45_at_1080p_and_scale_with_the_long_side():
    assert (fx.MemoryCanvas(1920, 1080).block_w, fx.MemoryCanvas(1920, 1080).block_h) == (48, 45)
    assert (fx.MemoryCanvas(640, 360).block_w, fx.MemoryCanvas(640, 360).block_h) == (16, 15)
    assert (fx.MemoryCanvas(3840, 2160).block_w, fx.MemoryCanvas(3840, 2160).block_h) == (96, 90)
    vertical = fx.MemoryCanvas(1080, 1920)  # long side 1920 -> the same block size, turned
    assert (vertical.block_w, vertical.block_h) == (48, 45)
    assert (fx.MemoryCanvas(1920, 1080).cols, fx.MemoryCanvas(1920, 1080).rows) == (40, 24)


def test_memory_canvas_with_refresh_1_reproduces_the_input():
    memory = fx.MemoryCanvas(W, H, refresh=1.0)
    for i in range(4):
        frame = _noise(i)
        assert np.array_equal(memory(frame, i / 25), frame)


def test_memory_canvas_with_refresh_0_holds_the_first_frame():
    memory = fx.MemoryCanvas(W, H, refresh=0.0, pale=0.0)
    first = _noise(0)
    memory(first, 0.0)
    for i in range(1, 5):
        assert np.array_equal(memory(_noise(i), i / 25), first)


def test_memory_canvas_never_returns_its_own_canvas():
    # A later effect writing into the returned frame in place must not be able
    # to rewrite the memory.
    memory = fx.MemoryCanvas(W, H, refresh=0.0, pale=0.0)
    first = _noise(0)
    memory(first, 0.0)
    out = memory(_noise(1), 0.04)
    out[:] = 0.0
    assert np.array_equal(memory(_noise(2), 0.08), first)


def test_stale_blocks_pale_toward_paper_with_age():
    paper = np.array([0.86, 0.85, 0.83], np.float32)
    memory = fx.MemoryCanvas(W, H, refresh=0.0, pale=0.55, fade_seconds=22.0, feather=0.0)
    first = _noise(0)
    memory(first, 0.0)
    distances = [float(np.abs(memory(_noise(1), t) - paper).mean()) for t in (1.0, 5.0, 11.0, 22.0)]
    assert distances == sorted(distances, reverse=True)
    # Fully aged, a block sits exactly `pale` of the way to paper.
    aged = memory(_noise(1), 40.0)
    np.testing.assert_allclose(aged, first * 0.45 + paper * 0.55, atol=1e-6)


def test_protected_ellipse_stays_live_while_the_rest_is_held():
    memory = fx.MemoryCanvas(W, H, refresh=0.0, pale=0.0, feather=0.0)
    first, second = _noise(0), _noise(1)
    memory(first, 0.0)
    out = memory(second, 0.04, protect=(32, 18, 8, 8))
    assert np.array_equal(out[18, 32], second[18, 32])  # the face: live
    assert np.array_equal(out[0, 0], first[0, 0])  # the world: remembered


def test_a_protected_ellipse_smaller_than_a_block_still_protects_its_centre():
    memory = fx.MemoryCanvas(W, H, refresh=0.0, pale=0.0, feather=0.0)
    memory(_noise(0), 0.0)
    second = _noise(1)
    out = memory(second, 0.04, protect=(33.3, 17.2, 0.5, 0.5))
    assert np.array_equal(out[17, 33], second[17, 33])


def test_the_face_forgets_when_protect_scale_reaches_zero():
    memory = fx.MemoryCanvas(W, H, refresh=0.0, pale=0.0, feather=0.0, protect_scale=[(0, 1.0), (1, 0.0)])
    first = _noise(0)
    memory(first, 0.0)
    out = memory(_noise(1), 2.0, protect=(32, 18, 8, 8))
    assert np.array_equal(out[18, 32], first[18, 32])


def test_a_full_beat_burst_can_make_every_block_remember():
    memory = fx.MemoryCanvas(W, H, refresh=0.0, pale=0.0, burst_beat=1.0)
    memory(_noise(0), 0.0)
    live = _noise(1)
    assert np.array_equal(memory(live, 0.04, beat=1.0), live)


def test_feather_softens_block_edges_and_zero_feather_keeps_them_hard():
    # 192x108 -> 5x4 px blocks; feather 30 (at 1080p) -> a 3 px soft edge.
    black, white = _solid((0, 0, 0), 108, 192), _solid((1, 1, 1), 108, 192)

    def mixed_values(feather):
        memory = fx.MemoryCanvas(192, 108, refresh=0.5, pale=0.0, feather=feather, seed=3)
        memory(black, 0.0)
        out = memory(white, 0.04)
        return int(((out > 0.01) & (out < 0.99)).sum())

    assert mixed_values(0.0) == 0
    assert mixed_values(30.0) > 0


def test_memory_canvas_is_deterministic_for_a_seed():
    def run(seed):
        memory = fx.MemoryCanvas(W, H, refresh=0.3, seed=seed)
        return [memory(_noise(i), i / 25, beat=0.5 if i % 3 == 0 else 0.0) for i in range(6)]

    a, b, c = run(5), run(5), run(6)
    assert all(np.array_equal(x, y) for x, y in zip(a, b))
    assert not all(np.array_equal(x, y) for x, y in zip(a, c))


def test_memory_canvas_state_dict_round_trip_resumes_bit_identically():
    frames = [_noise(i) for i in range(12)]

    def make():
        return fx.MemoryCanvas(W, H, refresh=0.35, pale=0.5, feather=3.0, seed=11)

    straight = make()
    expected = [straight(f, i / 25, onset=0.3) for i, f in enumerate(frames)]

    first_half = make()
    for i, f in enumerate(frames[:6]):
        first_half(f, i / 25, onset=0.3)
    saved = first_half.state_dict()

    resumed = make()
    resumed.load_state_dict(saved)
    got = [resumed(f, (i + 6) / 25, onset=0.3) for i, f in enumerate(frames[6:])]
    assert all(np.array_equal(x, y) for x, y in zip(got, expected[6:]))


def test_memory_canvas_state_survives_before_the_first_frame():
    memory = fx.MemoryCanvas(W, H)
    other = fx.MemoryCanvas(W, H)
    other.load_state_dict(memory.state_dict())
    assert other.canvas is None


def test_memory_canvas_refuses_a_checkpoint_from_another_size():
    saved = fx.MemoryCanvas(1920, 1080).state_dict()
    with pytest.raises(ValueError, match="block grid"):
        fx.MemoryCanvas(W, H).load_state_dict(saved)


def test_memory_canvas_refuses_wrong_frames():
    memory = fx.MemoryCanvas(W, H)
    with pytest.raises(ValueError):
        memory(_noise(0, h=H + 2), 0.0)
    with pytest.raises(TypeError, match="divide 8-bit frames by 255"):
        memory((_noise(0) * 255).astype(np.uint8), 0.0)


# --- generation_loss ------------------------------------------------------


def _midtones() -> np.ndarray:
    return np.clip(_noise(0) * 0.4 + 0.3, 0.0, 1.0).astype(np.float32)


def test_generation_loss_returns_a_float_frame_in_range():
    out = fx.generation_loss(_midtones(), 3, seed=1)
    assert out.shape == (H, W, 3) and out.dtype == np.float32
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_generation_loss_is_deterministic_for_a_seed():
    img = _midtones()
    assert np.array_equal(fx.generation_loss(img, 4, seed=2), fx.generation_loss(img, 4, seed=2))
    assert not np.array_equal(fx.generation_loss(img, 4, seed=2), fx.generation_loss(img, 4, seed=3))


def test_copies_get_paler_not_darker():
    """The release's first version went darker every generation and read as a
    burnt negative. Pale is the whole point."""
    img = _midtones()
    lum = [_luma(fx.generation_loss(img, g, seed=4)) for g in (0, 4, 12)]
    assert lum[0] < lum[1] < lum[2]


def test_copies_never_go_darker_than_the_original_even_at_high_generations():
    # The release's speckle rate grew without limit; uncapped, the toner
    # overtakes the lift and copies go darker than the original from the
    # mid-twenties on -- the burnt negative through the back door. Pins the
    # 1%-per-copy cap.
    img = _midtones()
    base = _luma(img)
    copy = img
    for k in range(40):
        copy = fx.generation_loss(copy, 1, seed=4, start=k)
        assert _luma(copy) >= base, f"generation {k + 1} went darker than the original"


def test_toner_speckle_appears_only_after_generation_8():
    grey = _solid((0.5, 0.5, 0.5))

    def specks(gens):
        out = fx.generation_loss(grey, gens, seed=1).mean(axis=2)
        return int((out < 0.7 * np.median(out)).sum())

    assert specks(8) == 0
    assert specks(9) > 0


def test_photocopying_a_held_frame_one_copy_at_a_time_matches_one_call():
    img = _midtones()
    batch = fx.generation_loss(img, 5, seed=9)
    held = img
    for k in range(5):
        held = fx.generation_loss(held, 1, seed=9, start=k)
    assert np.array_equal(held, batch)


def test_zero_generations_is_an_untouched_copy():
    img = _midtones()
    out = fx.generation_loss(img, 0)
    assert np.array_equal(out, img) and out is not img


# --- SlitScan -------------------------------------------------------------


def _ramp_frames(n: int) -> list[np.ndarray]:
    """Flat frames whose value encodes their index, so a column's delay is readable."""
    return [_solid((v, v, v)) for v in np.linspace(0.1, 0.9, n, dtype=np.float32)]


def test_slitscan_with_zero_offset_returns_the_current_frame():
    scan = fx.SlitScan(W, H, depth=8)
    for f in _ramp_frames(5):
        scan(f, 1.0)
    current = _noise(3)
    assert np.array_equal(scan(current, 0.0), current)


def test_slitscan_columns_get_older_away_from_the_anchor():
    frames = _ramp_frames(10)
    scan = fx.SlitScan(W, H, depth=8, anchor=0.0, ease=1.0)
    for f in frames:
        out = scan(f, 1.0)
    assert out[0, 0, 0] == frames[-1][0, 0, 0]  # at the anchor: live, exact
    assert out[0, -1, 0] == pytest.approx(frames[-8][0, 0, 0], abs=1 / 255)  # far edge: 7 frames back
    columns = out[0, :, 0]
    assert np.all(np.diff(columns) <= 0)  # older and older, never newer, toward the far edge


def test_slitscan_per_row_mode_delays_rows():
    frames = _ramp_frames(10)
    scan = fx.SlitScan(W, H, depth=8, axis="y", anchor=0.0)
    for f in frames:
        out = scan(f, 1.0)
    assert out[0, 5, 0] == frames[-1][0, 0, 0]
    assert out[-1, 5, 0] < out[0, 5, 0]
    assert np.array_equal(out[:, 0], out[:, -1])  # within a row, one moment


def test_slitscan_centre_anchor_keeps_the_middle_live():
    frames = _ramp_frames(10)
    scan = fx.SlitScan(W, H, depth=8, anchor=0.5)
    for f in frames:
        out = scan(f, 1.0)
    assert out[0, W // 2, 0] == frames[-1][0, 0, 0]
    assert out[0, 0, 0] < out[0, W // 2, 0] and out[0, -1, 0] < out[0, W // 2, 0]


def test_slitscan_warm_up_reads_only_frames_it_has():
    frames = _ramp_frames(3)
    scan = fx.SlitScan(W, H, depth=24, anchor=0.0)
    for f in frames:
        out = scan(f, 1.0)
    # Only three frames exist: the far edge shows the first, not an empty slot.
    assert out[0, -1, 0] == pytest.approx(frames[0][0, 0, 0], abs=1 / 255)


def test_slitscan_hold_region_stays_live():
    frames = _ramp_frames(10)
    scan = fx.SlitScan(W, H, depth=8, anchor=0.0)
    for f in frames[:-1]:
        scan(f, 1.0)
    out = scan(frames[-1], 1.0, hold=(56, 18, 6, 6))  # hold near the (oldest) right edge
    assert out[18, 56, 0] == frames[-1][0, 0, 0]
    assert out[0, 56, 0] < frames[-1][0, 0, 0]  # outside the hold: still smeared


def test_slitscan_accepts_a_mask_as_the_hold():
    scan = fx.SlitScan(W, H, depth=4)
    for f in _ramp_frames(4)[:-1]:
        scan(f, 1.0)
    current = _ramp_frames(4)[-1]
    mask = np.zeros((H, W), np.float32)
    mask[:, -8:] = 1.0
    out = scan(current, 1.0, hold=mask)
    assert np.array_equal(out[:, -8:], current[:, -8:])


def test_slitscan_state_dict_round_trip_resumes_bit_identically():
    frames = [_noise(i) for i in range(8)]
    straight = fx.SlitScan(W, H, depth=5)
    expected = [straight(f, 0.8) for f in frames]
    first = fx.SlitScan(W, H, depth=5)
    for f in frames[:4]:
        first(f, 0.8)
    resumed = fx.SlitScan(W, H, depth=5)
    resumed.load_state_dict(first.state_dict())
    got = [resumed(f, 0.8) for f in frames[4:]]
    assert all(np.array_equal(x, y) for x, y in zip(got, expected[4:]))


def test_slitscan_rejects_bad_arguments():
    with pytest.raises(ValueError):
        fx.SlitScan(W, H, axis="z")
    with pytest.raises(ValueError):
        fx.SlitScan(W, H, depth=0)
    with pytest.raises(ValueError):
        fx.SlitScan(W, H, depth=3).load_state_dict(fx.SlitScan(W, H, depth=4).state_dict())


# --- red_thread_grade -----------------------------------------------------


def _pixels(*rgb) -> np.ndarray:
    return np.array([list(rgb)], np.float32)


def test_red_thread_keeps_a_pure_red_pixel_and_drains_a_green_one():
    out = fx.red_thread_grade(_pixels((1, 0, 0), (0, 1, 0)))
    assert np.array_equal(out[0, 0], [1.0, 0.0, 0.0])  # red refuses to say goodbye
    green = out[0, 1]
    assert _chroma(green) < 0.15  # drained toward the two-tone world
    assert green[0] >= green[1]  # and no longer green


def test_red_thread_drains_skin_but_keeps_a_saturated_red():
    # Skin sits ~20 degrees from red at modest chroma; the defaults sit in that gap.
    skin, tie = (0.8, 0.6, 0.5), (0.7, 0.1, 0.12)
    out = fx.red_thread_grade(_pixels(skin, tie))
    assert _chroma(out[0, 0]) < 0.5 * _chroma(skin)
    np.testing.assert_allclose(out[0, 1], tie, atol=1e-6)


def test_red_thread_maps_darks_to_indigo_and_lights_to_bone():
    out = fx.red_thread_grade(_pixels((0, 0, 0), (1, 1, 1)))
    np.testing.assert_allclose(out[0, 0], (0.10, 0.09, 0.24), atol=1e-6)
    np.testing.assert_allclose(out[0, 1], (0.93, 0.89, 0.80), atol=1e-6)


def test_red_thread_can_protect_another_hue():
    out = fx.red_thread_grade(_pixels((1, 0, 0), (0, 1, 0)), protect_hue=120.0)
    assert np.array_equal(out[0, 1], [0.0, 1.0, 0.0])
    assert _chroma(out[0, 0]) < 0.5


def test_red_thread_amount_blends_from_the_original():
    img = _noise(2)
    assert np.array_equal(fx.red_thread_grade(img, amount=0.0), img)
    full = fx.red_thread_grade(img)
    np.testing.assert_allclose(fx.red_thread_grade(img, amount=0.5), 0.5 * img + 0.5 * full, atol=1e-6)


# --- KaleidoBloom ---------------------------------------------------------


def test_kaleido_bloom_at_amount_zero_is_a_no_op():
    img = _noise(0)
    assert np.array_equal(fx.KaleidoBloom()(img, 0.0), img)


def test_kaleido_index_maps_are_cached_by_size_k_and_centre():
    fx.kaleido_index_map.cache_clear()
    bloom = fx.KaleidoBloom(k=6)
    bloom(_noise(0), 1.0)
    bloom(_noise(1), 1.0)  # same size, k and centre: a hit
    info = fx.kaleido_index_map.cache_info()
    assert (info.hits, info.misses) == (1, 1)
    bloom(_noise(0, h=H * 2, w=W * 2), 1.0)  # a new size: a miss
    assert fx.kaleido_index_map.cache_info().misses == 2


def test_cached_index_maps_are_read_only():
    index = fx.kaleido_index_map(H, W, 6, W // 2, H // 2, 0.0)
    with pytest.raises(ValueError):
        index[0] = 0


def test_kaleido_bloom_is_mirror_symmetric_about_its_centre():
    out = fx.KaleidoBloom(k=4)(_noise(3), 1.0)
    assert (out == out[::-1]).all(axis=2).mean() > 0.99
    assert (out == out[:, ::-1]).all(axis=2).mean() > 0.99
    assert not np.array_equal(out, _noise(3))


def test_kaleido_bloom_mixes_by_amount():
    img = _noise(4)
    bloom = fx.KaleidoBloom(k=5)
    full = bloom(img, 1.0)
    np.testing.assert_allclose(bloom(img, 0.25), 0.75 * img + 0.25 * full, atol=1e-6)


def test_kaleido_needs_a_wedge():
    with pytest.raises(ValueError):
        fx.kaleido_index_map(H, W, 0, 1, 1, 0.0)


# --- GrainBank ------------------------------------------------------------


def test_grain_bank_is_deterministic_for_a_seed():
    a, b, c = fx.GrainBank(W, H, seed=3), fx.GrainBank(W, H, seed=3), fx.GrainBank(W, H, seed=4)
    first = [a.sample() for _ in range(3)]
    assert all(np.array_equal(x, b.sample()) for x in first)
    assert not np.array_equal(first[0], c.sample())


def test_grain_bank_samples_are_zero_mean_luminance_grain():
    grain = fx.GrainBank(W, H).sample()
    assert grain.shape == (H, W, 1) and grain.dtype == np.float32
    assert abs(float(grain.mean())) < 0.2


def test_grain_is_stronger_on_darker_frames_and_stays_in_range():
    bank = fx.GrainBank(W, H, seed=1)
    dark, light = _solid((0.3, 0.3, 0.3)), _solid((0.7, 0.7, 0.7))
    dark_spread = float((bank(dark) - dark).std())
    light_spread = float((bank(light) - light).std())
    assert dark_spread > 1.1 * light_spread
    out = bank(_noise(0), 0.5)
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_zero_grain_leaves_the_frame_alone():
    img = _noise(1)
    assert np.array_equal(fx.GrainBank(W, H)(img, 0.0), img)


def test_grain_bank_state_dict_resumes_the_same_picks():
    straight = fx.GrainBank(W, H, seed=5)
    expected = [straight.sample() for _ in range(3)]
    first = fx.GrainBank(W, H, seed=5)
    first.sample()
    resumed = fx.GrainBank(W, H, seed=5)
    resumed.load_state_dict(first.state_dict())
    assert np.array_equal(resumed.sample(), expected[1])
    assert np.array_equal(resumed.sample(), expected[2])


def test_grain_bank_needs_a_tile():
    with pytest.raises(ValueError):
        fx.GrainBank(W, H, tiles=0)


# --- feedback_echo / punch_zoom ------------------------------------------


def _dot(x: int, y: int) -> np.ndarray:
    img = np.zeros((H, W, 3), np.float32)
    img[y, x] = 1.0
    return img


def _brightest(img: np.ndarray) -> tuple[int, int]:
    y, x = np.unravel_index(int(np.argmax(img[..., 0])), img.shape[:2])
    return int(x), int(y)


def test_feedback_echo_without_a_previous_frame_is_the_current_one():
    cur = _noise(0)
    assert np.array_equal(fx.feedback_echo(None, cur), cur)
    assert np.array_equal(fx.feedback_echo(_noise(1), cur, mix=0.0), cur)


def test_feedback_echo_blends_in_the_previous_output():
    prev, cur = _noise(0), _noise(1)
    np.testing.assert_allclose(fx.feedback_echo(prev, cur, zoom=1.0, mix=0.3), 0.7 * cur + 0.3 * prev, atol=1e-6)
    assert np.array_equal(fx.feedback_echo(prev, cur, zoom=1.0, mix=1.0), prev)


def test_feedback_echo_lighten_only_lets_highlights_trail():
    dark, bright = _solid((0.2, 0.2, 0.2)), _solid((0.9, 0.9, 0.9))
    out = fx.feedback_echo(bright, dark, zoom=1.0, mix=1.0, lighten=True, decay=0.88)
    np.testing.assert_allclose(out, 0.9 * 0.88, atol=1e-6)  # a bright ghost, decayed
    out = fx.feedback_echo(dark, bright, zoom=1.0, mix=1.0, lighten=True)
    assert np.array_equal(out, bright)  # a darker ghost never shows


def test_feedback_zoom_pushes_the_ghost_outward():
    out = fx.feedback_echo(_dot(50, 18), np.zeros((H, W, 3), np.float32), zoom=1.2, mix=1.0)
    x, y = _brightest(out)
    assert x > 50 and y == 18


def test_punch_zoom_at_zero_is_a_no_op_and_otherwise_scales_about_the_centre():
    img = _dot(50, 18)
    assert np.array_equal(fx.punch_zoom(img, 0.0), img)
    x, y = _brightest(fx.punch_zoom(img, 0.2))
    assert (x, y) == (54, 18)  # (50.5 - 32) * 1.2 + 32 = 54.2


def test_punch_zoom_about_a_point_keeps_that_point_still():
    img = _dot(10, 9)
    x, y = _brightest(fx.punch_zoom(img, 0.3, center=(10.5, 9.5)))
    assert (x, y) == (10, 9)


def test_zooming_out_is_refused():
    with pytest.raises(ValueError):
        fx.feedback_echo(_noise(0), _noise(1), zoom=0.9)


# --- mean_face ------------------------------------------------------------

FACE_H, FACE_W = 64, 96
TARGET_L = (0.415 * FACE_W, 0.40 * FACE_H)
TARGET_R = (0.585 * FACE_W, 0.40 * FACE_H)


def _face(eyes, h: int = FACE_H, w: int = FACE_W) -> np.ndarray:
    """A synthetic 'face': two soft bright dots where the eyes are, on black."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    img = np.zeros((h, w), np.float32)
    for x, y in eyes:
        img += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.5**2))
    return np.repeat(np.clip(img, 0.0, 1.0)[..., None], 3, axis=2)


def _value_at(img, point) -> float:
    return float(img[int(point[1]), int(point[0]), 0])


def test_mean_face_aligns_faces_by_their_eyes():
    # Two faces at different positions, scales and tilts: aligned, their eyes
    # land on the same target pixels and the mean is sharp there.
    eyes_a = ((30.0, 30.0), (50.0, 30.0))
    eyes_b = ((20.0, 20.0), (60.0, 40.0))
    mean = fx.mean_face([_face(eyes_a), _face(eyes_b)], [eyes_a, eyes_b])
    assert mean.shape == (FACE_H, FACE_W, 3) and mean.dtype == np.float32
    assert _value_at(mean, TARGET_L) > 0.8
    assert _value_at(mean, TARGET_R) > 0.8
    # Where face B's eyes were in its own frame, the aligned mean is dark.
    assert _value_at(mean, (20.5, 20.5)) < 0.1


def test_unaligned_average_would_blur_the_eyes():
    # The control for the test above: averaging without alignment smears.
    eyes_a = ((30.0, 30.0), (50.0, 30.0))
    eyes_b = ((20.0, 20.0), (60.0, 40.0))
    naive = (_face(eyes_a) + _face(eyes_b)) / 2
    assert naive.max() <= 0.5 + 1e-6


def test_mean_face_skips_missing_and_implausible_eyes():
    good = ((30.0, 30.0), (50.0, 30.0))
    glitch = ((30.0, 30.0), (31.0, 30.0))  # eyes 1 px apart: a detector glitch
    acc = fx.MeanFace(FACE_W, FACE_H)
    assert acc.add(_face(good), good)
    assert not acc.add(_face(good), glitch)
    assert not acc.add(_face(good), None)
    assert (acc.count, acc.rejected) == (1, 2)


def test_mean_face_accepts_8_bit_frames_and_an_output_size():
    eyes = ((30.0, 30.0), (50.0, 30.0))
    frame = (_face(eyes) * 255 + 0.5).astype(np.uint8)
    mean = fx.mean_face([frame], [eyes], size=(48, 32))
    assert mean.shape == (32, 48, 3)
    # Shrunk 2.4x, each eye is a sub-pixel dot: check where the brightest
    # point lands rather than one pixel's value.
    x, y = _brightest(mean[:, :24])  # the left half holds the left eye
    assert abs(x + 0.5 - 0.415 * 48) <= 1.0 and abs(y + 0.5 - 0.40 * 32) <= 1.0


def test_mean_face_accumulator_resumes_from_its_state():
    eyes_a = ((30.0, 30.0), (50.0, 30.0))
    eyes_b = ((20.0, 20.0), (60.0, 40.0))
    straight = fx.MeanFace(FACE_W, FACE_H)
    straight.add(_face(eyes_a), eyes_a)
    straight.add(_face(eyes_b), eyes_b)
    first = fx.MeanFace(FACE_W, FACE_H)
    first.add(_face(eyes_a), eyes_a)
    resumed = fx.MeanFace(FACE_W, FACE_H)
    resumed.load_state_dict(first.state_dict())
    resumed.add(_face(eyes_b), eyes_b)
    assert np.array_equal(resumed.result(), straight.result())


def test_mean_face_with_nothing_accepted_says_why():
    with pytest.raises(ValueError, match="no frame was accepted"):
        fx.mean_face([_face(((30, 30), (50, 30)))], [None])
    with pytest.raises(ValueError, match="at least one frame"):
        fx.mean_face([], [])
    with pytest.raises(ValueError):
        fx.MeanFace(FACE_W, FACE_H).load_state_dict(fx.MeanFace(10, 10).state_dict())
