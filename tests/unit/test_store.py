import hmac

import pytest

from cloud_crawler_lab import store as store_module
from cloud_crawler_lab.store import ItemTooLarge, UploadStore

FILES = {"report.md": b"x" * 100}
META = {"k": "v"}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(ttl=120, items=200, size=10_000, clock=None):
    return UploadStore(ttl, items, size, clock=clock or Clock())


def test_put_and_get_with_the_owner_token():
    store = make()
    stored = store.put(META, FILES)
    assert len(stored.owner_token) >= 32 and stored.evicted == 0
    view = store.get(stored.id, stored.owner_token)
    assert view is not None and view.meta == META and view.files == FILES and view.expires_at == stored.expires_at
    assert store.size == 1 and store.bytes_used == 100


def test_only_the_owner_token_opens_a_result_and_every_refusal_looks_the_same():
    store = make()
    mine, theirs = store.put(META, FILES), store.put({"k": "other"}, FILES)
    assert store.get(mine.id, theirs.owner_token) is None, "another visitor's token"
    assert store.get(mine.id, None) is None and store.get(mine.id, "") is None
    assert store.get(mine.id, "x" * 10_000) is None
    assert store.get("00000000-0000-0000-0000-000000000099", mine.owner_token) is None, "an id that does not exist"
    assert store.get("", mine.owner_token) is None
    assert store.get(mine.id, mine.owner_token) is not None
    assert not store.delete(mine.id, theirs.owner_token) and store.size == 2


def test_the_token_is_kept_only_as_a_hash_and_compared_in_constant_time(monkeypatch):
    store = make()
    stored = store.put(META, FILES)
    entry = next(iter(store._items.values()))
    assert stored.owner_token.encode() not in entry.token_hash and len(entry.token_hash) == 32
    assert stored.owner_token not in repr(vars(entry))
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(store_module.hmac, "compare_digest", lambda a, b: calls.append((a, b)) or real(a, b))
    store.get(stored.id, stored.owner_token)
    assert len(calls) == 1 and all(isinstance(side, bytes) for side in calls[0])


def test_ids_and_tokens_are_random():
    store = make()
    first, second = store.put(META, FILES), store.put(META, FILES)
    assert first.id != second.id and first.owner_token != second.owner_token
    assert len(first.id) == 36 and first.id[14] == "4", "a version 4 UUID"


def test_a_result_expires_after_the_time_to_live_and_the_sweep_removes_it():
    clock = Clock()
    store = make(ttl=120, clock=clock)
    stored = store.put(META, FILES)
    clock.now += 119
    assert store.get(stored.id, stored.owner_token) is not None
    clock.now += 2
    assert store.get(stored.id, stored.owner_token) is None, "refused before any sweep has run"
    assert store.size == 1 and store.sweep() == 1 and store.size == 0 and store.bytes_used == 0


def test_the_oldest_results_go_first_when_the_item_limit_is_reached():
    clock = Clock()
    store = make(items=3, clock=clock)
    kept = []
    for _ in range(4):
        clock.now += 1
        kept.append(store.put(META, FILES))
    assert store.size == 3 and kept[-1].evicted == 1
    assert store.get(kept[0].id, kept[0].owner_token) is None
    assert all(store.get(s.id, s.owner_token) for s in kept[1:])


def test_the_oldest_results_go_first_when_the_byte_budget_would_be_exceeded():
    clock = Clock()
    store = make(items=200, size=250, clock=clock)
    first = store.put(META, FILES)
    clock.now += 1
    second = store.put(META, FILES)
    clock.now += 1
    third = store.put(META, FILES)
    assert third.evicted == 1 and store.size == 2 and store.bytes_used == 200
    assert store.get(first.id, first.owner_token) is None and store.get(second.id, second.owner_token)


def test_a_result_bigger_than_the_whole_store_is_refused_and_evicts_nothing():
    store = make(size=150)
    kept = store.put(META, FILES)
    with pytest.raises(ItemTooLarge):
        store.put(META, {"report.md": b"x" * 151})
    assert store.get(kept.id, kept.owner_token) is not None and store.size == 1


def test_delete_and_clear_release_everything():
    store = make()
    stored = store.put(META, FILES)
    assert store.delete(stored.id, stored.owner_token) and store.size == 0 and store.bytes_used == 0
    assert not store.delete(stored.id, stored.owner_token)
    store.put(META, FILES)
    store.put(META, FILES)
    assert store.clear() == 2 and store.size == 0 and store.bytes_used == 0


def test_a_client_that_keeps_uploading_loses_its_own_oldest_results_first():
    clock = Clock()
    store = UploadStore(120, 100, 100_000, per_owner_items=2, clock=clock)
    theirs = store.put(META, FILES, owner="b")
    clock.now += 1
    mine = []
    for _ in range(4):
        clock.now += 1
        mine.append(store.put(META, FILES, owner="a"))
    assert [store.get(m.id, m.owner_token) is not None for m in mine] == [False, False, True, True]
    assert store.get(theirs.id, theirs.owner_token) is not None, "someone else's result is not touched"
    assert mine[-1].evicted == 1 and store.size == 3


def test_a_client_is_held_to_a_share_of_the_bytes_too():
    clock = Clock()
    store = UploadStore(120, 100, 1000, per_owner_items=50, per_owner_bytes=250, clock=clock)
    other = store.put(META, FILES, owner="b")
    results = []
    for _ in range(4):
        clock.now += 1
        results.append(store.put(META, FILES, owner="a"))  # 100 bytes each: two fit in 250
    assert [store.get(r.id, r.owner_token) is not None for r in results] == [False, False, True, True]
    assert store.get(other.id, other.owner_token) is not None


def test_the_share_defaults_to_a_tenth_of_the_items_and_a_quarter_of_the_bytes():
    store = UploadStore(120, 200, 64 * 1024 * 1024)
    assert store._per_owner_items == 20 and store._per_owner_bytes == 16 * 1024 * 1024
    assert UploadStore(120, 5, 10)._per_owner_items == 1


def test_a_result_without_an_owner_key_has_no_share_to_exceed():
    store = make(items=5)
    for _ in range(5):
        store.put(META, FILES)
    assert store.size == 5
