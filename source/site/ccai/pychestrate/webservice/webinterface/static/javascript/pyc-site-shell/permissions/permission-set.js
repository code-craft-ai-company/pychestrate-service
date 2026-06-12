class PermissionSet {
  _keys;
  /**
   * Construct a permission set from an iterable of permission
   * keys. Duplicates are de-duplicated by the underlying Set.
   *
   * @param keys - Iterable of permission key strings.
   */
  constructor(keys) {
    this._keys = /* @__PURE__ */ new Set();
    for (const key of keys) {
      if (typeof key === "string" && key.length > 0) {
        this._keys.add(key);
      }
    }
  }
  /**
   * Return true when the supplied permission key is present.
   *
   * @param perm - Permission key.
   */
  has(perm) {
    const rtnval = this._keys.has(perm);
    return rtnval;
  }
  /**
   * Return true when every supplied permission key is present.
   * The empty-array case returns true (vacuously satisfied).
   *
   * @param perms - Iterable of permission keys.
   */
  hasAll(perms) {
    for (const perm of perms) {
      if (this._keys.has(perm) === false) {
        return false;
      }
    }
    return true;
  }
  /**
   * Return the diff between this set and another.
   *
   * @param other - Comparison set.
   * @returns Object with `added` (keys in other but not this)
   *          and `removed` (keys in this but not other) string
   *          arrays. Both arrays are sorted for determinism.
   */
  diff(other) {
    const added = [];
    const removed = [];
    for (const key of other._keys) {
      if (this._keys.has(key) === false) {
        added.push(key);
      }
    }
    for (const key of this._keys) {
      if (other._keys.has(key) === false) {
        removed.push(key);
      }
    }
    added.sort();
    removed.sort();
    const rtnval = { added, removed };
    return rtnval;
  }
  /**
   * Return the cardinality of the underlying key set.
   */
  size() {
    const rtnval = this._keys.size;
    return rtnval;
  }
  /**
   * Return the underlying keys as a sorted array snapshot.
   * Intended for logging / diagnostics. Do NOT use as a security
   * boundary — sidebar visibility is UX only.
   */
  toSortedArray() {
    const rtnval = Array.from(this._keys).sort();
    return rtnval;
  }
}
export {
  PermissionSet
};
