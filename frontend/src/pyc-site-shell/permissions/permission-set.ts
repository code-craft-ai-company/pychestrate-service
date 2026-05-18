/**
 * Value object wrapping the set of permission keys held by the
 * current principal.
 *
 * Per the 9-site-shell design doc:
 *
 * - `has(perm)` — single-key check.
 * - `hasAll(perms)` — every key must be present.
 * - `diff(other)` — `{added, removed}` between two snapshots.
 *
 * Instances are immutable. Mutation requires constructing a new
 * instance.
 */
export class PermissionSet {
    private readonly _keys: Set<string>

    /**
     * Construct a permission set from an iterable of permission
     * keys. Duplicates are de-duplicated by the underlying Set.
     *
     * @param keys - Iterable of permission key strings.
     */
    public constructor(keys: Iterable<string>) {
        this._keys = new Set<string>()
        for (const key of keys) {
            if (typeof key === "string" && key.length > 0) {
                this._keys.add(key)
            }
        }
    }

    /**
     * Return true when the supplied permission key is present.
     *
     * @param perm - Permission key.
     */
    public has(perm: string): boolean {
        const rtnval = this._keys.has(perm)
        return rtnval
    }

    /**
     * Return true when every supplied permission key is present.
     * The empty-array case returns true (vacuously satisfied).
     *
     * @param perms - Iterable of permission keys.
     */
    public hasAll(perms: readonly string[]): boolean {
        for (const perm of perms) {
            if (this._keys.has(perm) === false) {
                return false
            }
        }
        return true
    }

    /**
     * Return the diff between this set and another.
     *
     * @param other - Comparison set.
     * @returns Object with `added` (keys in other but not this)
     *          and `removed` (keys in this but not other) string
     *          arrays. Both arrays are sorted for determinism.
     */
    public diff(other: PermissionSet): { added: string[]; removed: string[] } {
        const added: string[] = []
        const removed: string[] = []
        for (const key of other._keys) {
            if (this._keys.has(key) === false) {
                added.push(key)
            }
        }
        for (const key of this._keys) {
            if (other._keys.has(key) === false) {
                removed.push(key)
            }
        }
        added.sort()
        removed.sort()
        const rtnval = { added, removed }
        return rtnval
    }

    /**
     * Return the cardinality of the underlying key set.
     */
    public size(): number {
        const rtnval = this._keys.size
        return rtnval
    }

    /**
     * Return the underlying keys as a sorted array snapshot.
     * Intended for logging / diagnostics. Do NOT use as a security
     * boundary — sidebar visibility is UX only.
     */
    public toSortedArray(): string[] {
        const rtnval = Array.from(this._keys).sort()
        return rtnval
    }
}
