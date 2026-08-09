from pymilvus import (
    MilvusClient,
    DataType,
    Function,
    FunctionType,
)

client = MilvusClient(
    db_name = "aigc_rag_milvus",
    uri="http://106.14.181.222:19530",
)

COLLECTION_NAME = "aigc_parent_docs"

FIELD_CHUNK_ID = "chunk_id"
FIELD_BIZ_ID = "biz_id"
FIELD_CREATED_AT = "created_at"
FIELD_INDEX_ID = "index_id"
FIELD_TEXT = "text"
FIELD_SPARSE = "text_sparse"


def init_parent_collection_bm25():
    """
    创建父块 collection：
    - 不包含 dense 向量
    - 保留 BM25 sparse 检索能力
    - 可用于关键词检索 + 回表 text
    """

    if client.has_collection(collection_name=COLLECTION_NAME):
        client.drop_collection(collection_name=COLLECTION_NAME)

    schema = client.create_schema(
        auto_id=True,
        enable_dynamic_field=False,
    )

    schema.add_field(
        field_name="id",
        datatype=DataType.INT64,
        is_primary=True,
        auto_id=True,
    )

    schema.add_field(
        field_name=FIELD_CHUNK_ID,
        datatype=DataType.VARCHAR,
        max_length=128,
    )
    schema.add_field(
        field_name=FIELD_BIZ_ID,
        datatype=DataType.VARCHAR,
        max_length=128,
    )
    schema.add_field(
        field_name=FIELD_CREATED_AT,
        datatype=DataType.INT64,   # epoch_millis
    )
    schema.add_field(
        field_name=FIELD_INDEX_ID,
        datatype=DataType.DOUBLE,
    )
    schema.add_field(
        field_name=FIELD_TEXT,
        datatype=DataType.VARCHAR,
        max_length=65535,
        enable_analyzer=True,
    )
    schema.add_field(
        field_name=FIELD_SPARSE,
        datatype=DataType.SPARSE_FLOAT_VECTOR,
    )

    schema.add_function(
        Function(
            name="bm25_fn",
            function_type=FunctionType.BM25,
            input_field_names=[FIELD_TEXT],
            output_field_names=[FIELD_SPARSE],
        )
    )

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name=FIELD_SPARSE,
        index_name="text_sparse_index",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25",
        params={"inverted_index_algo": "DAAT_MAXSCORE"},
    )

    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params,
    )

    client.load_collection(collection_name=COLLECTION_NAME)
    print(f"[OK] collection created: {COLLECTION_NAME}")


if __name__ == "__main__":
    init_parent_collection_bm25()
