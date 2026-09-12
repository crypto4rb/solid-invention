import streamlit as st

from src.auth import get_user_options, get_user
from src.policy import detect_forbidden_query, get_allowed_scope_summary
from src.router import route_query
from src.rag_retriever import retrieve_rag_context
from src.generator import generate_rag_answer
from src.audit import write_audit_log

st.set_page_config(
    page_title="Enterprise RAG Intelligence",
    page_icon="🔐",
    layout="wide"
)

st.title("🔐 Enterprise RAG Intelligence Assistant")
st.caption("Secure RAG over documents, CSV records, JSON logs, and uploaded enterprise files with RBAC enforcement.")

with st.sidebar:
    st.header("User Context")

    user_options = get_user_options()
    selected_user_label = st.selectbox("Select user role", list(user_options.keys()))
    user_id = user_options[selected_user_label]
    user = get_user(user_id)

    st.write("### Active User")
    st.json(user)

    st.write("### Allowed Scope")
    st.json(get_allowed_scope_summary(user))

    st.divider()

    st.write("### Demo Queries")
    st.code("What was total vendor spend in Q1 and what approval policy applies?")
    st.code("Summarize the API incident and related error logs.")
    st.code("Show me employee salaries.")
    st.code("Were there failed login attempts before the payment alert?")

st.info(
    "Before running queries, generate data and ingest it:\n\n"
    "`python scripts/generate_dataset.py`\n\n"
    "`python scripts/ingest_rag.py`"
)

query = st.text_area(
    "Ask an enterprise question",
    placeholder="Example: What was total vendor spend in Q1 and what approval policy applies?",
    height=100
)

run = st.button("Run Secure RAG Query", type="primary")

if run:
    if not query.strip():
        st.warning("Query daal bhai. Empty query pe RAG bhi hawa nahi chaba sakta.")
        st.stop()

    route_result = route_query(query)

    forbidden_result = detect_forbidden_query(user, query)
    forbidden_result["scope"] = get_allowed_scope_summary(user)

    rag_result = {"results": [], "denied_results": []}

    if not forbidden_result["forbidden"]:
        rag_result = retrieve_rag_context(
            user=user,
            query=query,
            route_sources=route_result["routes"],
            top_k=5
        )

    answer_result = generate_rag_answer(
        query=query,
        user=user,
        route_result=route_result,
        rag_result=rag_result,
        forbidden_result=forbidden_result
    )

    trace = {
        "intent": route_result["intent"],
        "routes": route_result["routes"],
        "rbac_role": user["role"],
        "forbidden_query_detected": forbidden_result["forbidden"],
        "chunks_retrieved": [
            {
                "file_name": r["metadata"].get("file_name"),
                "source_type": r["metadata"].get("source_type"),
                "department": r["metadata"].get("department"),
                "sensitivity": r["metadata"].get("sensitivity"),
                "score": r["score"],
                "citation": r["citation"]
            }
            for r in rag_result.get("results", [])
        ],
        "denied_candidates": rag_result.get("denied_results", [])
    }

    write_audit_log(user, query, route_result, answer_result, trace)

    col1, col2 = st.columns([2, 1])

    with col1:
        if answer_result["status"] == "denied":
            st.error("Access Denied")
        elif answer_result["status"] == "no_answer":
            st.warning("No Authorized Answer Found")
        else:
            st.success("Answer Generated From Authorized RAG Context")

        st.subheader("Answer")
        st.write(answer_result["answer"])

        st.subheader("Citations")
        if answer_result["citations"]:
            for citation in answer_result["citations"]:
                st.write(f"- `{citation}`")
        else:
            st.write("No citations available.")

    with col2:
        st.subheader("Confidence")
        confidence = answer_result["confidence"]

        if confidence == "high":
            st.success("High")
        elif confidence == "medium":
            st.warning("Medium")
        else:
            st.error("Low")

        st.subheader("Retrieval Trace")
        st.json(trace)

        st.subheader("Route Result")
        st.json(route_result)