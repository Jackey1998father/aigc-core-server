
from pymilvus import (
    MilvusClient,
    DataType,
    Function,
    FunctionType,
)

milvus_client = MilvusClient(
    db_name = "aigc_rag_milvus",
    uri="http://106.14.181.222:19530",
)
def init_bge_collection(collection_name , drop_if_exists: bool = False ):
    if  milvus_client.has_collection(collection_name= collection_name):
        if drop_if_exists:
             milvus_client.drop_collection(collection_name= collection_name)
        else:
            return

    # ====== schema ======
    schema =  milvus_client.create_schema(
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
        field_name="chunk_id",
        datatype=DataType.VARCHAR,
        max_length=128,
    )

    schema.add_field(
        field_name="biz_id",
        datatype=DataType.VARCHAR,
        max_length=128,
    )

    schema.add_field(
        field_name="index_id",
        datatype=DataType.DOUBLE,
    )

    schema.add_field(
        field_name="text",
        datatype=DataType.VARCHAR,
        max_length=65535,
        enable_analyzer=True,  # 混合检索里建议开
    )

    # dense vector
    schema.add_field(
        field_name="vector",
        datatype=DataType.FLOAT_VECTOR,
        dim=1024,
    )

    # sparse vector（由 BM25 function 自动生成）
    schema.add_field(
        field_name="text_sparse",
        datatype=DataType.SPARSE_FLOAT_VECTOR,
    )

    # BM25 function: text -> text_sparse
    schema.add_function(
        Function(
            name="bm25_fn",
            function_type=FunctionType.BM25,
            input_field_names=["text"],
            output_field_names=["text_sparse"],
        )
    )

    # ====== index params ======
    index_params =  milvus_client.prepare_index_params()

    # dense index
    index_params.add_index(
        field_name="vector",
        index_name="vector_index",
        index_type="AUTOINDEX",
        metric_type="COSINE",  # 你原来就是 COSINE，这里保持一致
    )

    # sparse index
    index_params.add_index(
        field_name="text_sparse",
        index_name="text_sparse_index",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25",
        params={"inverted_index_algo": "DAAT_MAXSCORE"},
    )

    # ====== create & load ======
    milvus_client.create_collection(
        collection_name= collection_name,
        schema=schema,
        index_params=index_params,
    )

    milvus_client.load_collection(collection_name= collection_name)

if __name__ == "__main__":
    init_bge_collection(collection_name = "aigc_docs_bge")
