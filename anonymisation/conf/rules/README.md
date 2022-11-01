# Rule Development and ChangeLog

## Postcodes

The original postcode regex (with doubled escapes for JSON) was:

```
"([^\\n]{0,}(([Gg][Ii][Rr] 0[Aa]{2})|((([A-Za-z][0-9]{1,2})|(([A-Za-z][A-Ha-hJ-Yj-y][0-9]{1,2})|(([A-Za-z][0-9][A-Za-z])|([A-Za-z][A-Ha-hJ-Yj-y][0-9]?[A-Za-z]))))\\s?(?![0-9]mm)[0-9][A-Za-z]{2})))",
```

Note that it has `[\n]{0,}` at the start so it will redact the whole line leading up to the postcode on the assumption that it's a single-line address.

The problem is that
* it matches "the 6th" as a postcode simply because the second half matches
* it matches toad12as" because it has no anchors (should only match "to ad12as")

Research https://stackoverflow.com/questions/164979/regex-for-matching-uk-postcodes

The main answer came up with a simplified pattern `^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$`
but I fear that's too simplistic with its use of `[A-Z]`.

The second answer came up with `^(((([A-PR-UWYZ][A-HK-Y]?[0-9][0-9]?)|(([A-PR-UWYZ][0-9][A-HJKSTUW])|([A-PR-UWYZ][A-HK-Y][0-9][ABEHMNPRV-Y]))) {0,1}[0-9][ABD-HJLNP-UW-Z]{2}))$` which looks more sensible.

* Removed `GIR 0AA` which is not used any more and is not PII (it's the old Girobank)
* Ignored non-UK postcodes (eg. Falkland Islands)
* Inserted the `(?![0-9]mm)` to exclude lines with dimensions
* Prepended the `[\n]{0,}` to match the line up to the postcode
* Inserted a `\b` to prevent run-in

Final pattern (with doubled escapes for JSON file)

```
([^\\n]{0,}\\b(((([A-PR-UWYZ][A-HK-Y]?[0-9][0-9]?)|(([A-PR-UWYZ][0-9][A-HJKSTUW])|([A-PR-UWYZ][A-HK-Y][0-9][ABEHMNPRV-Y]))) {0,1}(?![0-9]mm)[0-9][ABD-HJLNP-UW-Z]{2})))
```
