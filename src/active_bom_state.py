import pandas as pd

from main import build_review_items


class ActiveBomState:
    """
    The single canonical representation of a run's processed BOM.

    This wraps the same DataFrame object produced by the cleaning/sourcing/
    PartsBox steps -- it does not copy it. Review items and results views
    must be *derived* from this object on demand, not materialized once
    into a second, independently-tracked dataset that could drift out of
    sync with it.

    The eventual replacement-selection flow (Phase 3+, not built yet) must
    go through update_row() so every derived view -- review, results,
    purchasing, exports -- reflects a change the moment it is made,
    instead of some views being refreshed and others left stale.
    """

    def __init__(self, dataframe, run_id):
        self.run_id = run_id
        # Same object, not a copy. Sourcing/PartsBox steps that already
        # hold a reference to this DataFrame keep seeing every future
        # change made through update_row().
        self.dataframe = dataframe

    def row_id_for_index(self, index):
        return f"{self.run_id}:{index}"

    def index_for_row_id(self, row_id):
        prefix = f"{self.run_id}:"
        row_id = str(row_id)
        if not row_id.startswith(prefix):
            return None

        raw_index = row_id[len(prefix):]
        try:
            return int(raw_index)
        except ValueError:
            return raw_index

    def rows(self):
        """Every canonical row, as JSON-safe dicts with a stable row_id."""
        return self.to_records(self.dataframe)

    def review_items_dataframe(self):
        """
        Rows needing review, derived fresh from the canonical DataFrame via
        the existing shared build_review_items() -- reused, not
        reimplemented, so review criteria stay in one place.
        """
        return build_review_items(self.dataframe)

    def review_items(self):
        """Rows needing review, as JSON-safe dicts sharing row_id with rows()."""
        return self.to_records(self.review_items_dataframe())

    def get_row(self, row_id):
        index = self.index_for_row_id(row_id)
        if index is None or index not in self.dataframe.index:
            return None

        record = self.dataframe.loc[index].to_dict()
        record["row_id"] = row_id
        return record

    def update_row(self, row_id, updates):
        """
        The one shared operation through which a row in the canonical
        state may be changed. Every derived view (rows(), review_items(),
        and anything exported from self.dataframe) reflects the change
        immediately, because they all read from this same DataFrame --
        there is no second copy to fall out of sync.
        """
        index = self.index_for_row_id(row_id)
        if index is None or index not in self.dataframe.index:
            raise KeyError(f"Unknown row_id: {row_id}")

        for column, value in updates.items():
            self.dataframe.at[index, column] = value

        return self.get_row(row_id)

    def to_records(self, dataframe):
        """
        Shared dict-conversion used for both rows() and review_items(), so
        the two transport representations are always built the same way
        from whatever DataFrame is handed in -- never two divergent
        implementations.
        """
        if dataframe is None or dataframe.empty:
            return []

        safe_df = dataframe.where(pd.notnull(dataframe), "")
        records = []
        for index, record in safe_df.to_dict("index").items():
            record = dict(record)
            record["row_id"] = self.row_id_for_index(index)
            records.append(record)

        return records
