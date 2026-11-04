# Custom Pack addresses

New Packs and imported copies accept an optional `short_name`. A blank value
keeps automatic generation. The user's base is followed by `_by_<bot_username>`;
the complete name has at most 64 characters, starts with an English letter, and
contains only English letters, digits and single underscores. The base cannot
end with an underscore because the suffix begins with one.

The authenticated `GET /api/packs/name-availability?short_name=...` endpoint
returns the final name, suffix, base length limit and availability. The browser
checks after 350 ms without typing and ignores obsolete responses. Invalid,
occupied and failed checks prevent submitting a custom address. Creation checks
again and reserves the name case-insensitively across all local users in a
SQLite transaction. A Telegram failure is never treated as availability.

A local draft does not create or reserve an empty Telegram set: Telegram requires
at least one initial sticker. Availability may change before the first
Publication or import. Those operations reject unrelated existing contents;
Publication still reconciles a previously uploaded sticker after a lost response.
Deleting an unconfirmed empty draft checks Telegram first. If the remote set
exists, deletion returns a conflict and preserves both records: retry Publication
or import to reconcile an ambiguous create response, then delete the confirmed
Pack. If the remote set is absent, only the local draft is removed. An unrelated
remote collision also blocks draft deletion until the conflict is resolved;
the application never deletes that set merely because its address matches.

Source: [Telegram Bot API: createNewStickerSet](https://core.telegram.org/bots/api#createnewstickerset),
checked 2026-11-04. Telegram remains authoritative when creating the set.
