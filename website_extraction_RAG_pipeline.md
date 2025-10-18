### **Blueprint Part 1: Intelligent Sourcing & Re-ranking for Project Orion**

This document details the state-of-the-art "Sourcing" phase of the RAG pipeline. The objective is to move beyond a simple API call and create an intelligent, multi-stage funnel that identifies the most relevant, trustworthy, and high-quality URLs from the live internet *before* committing to the resource-intensive extraction process.

---

### **Stage 1: Query Transformation & Expansion**

The quality of the search results is directly dependent on the quality of the search queries. This stage refines the user's raw prompt into a set of optimized queries.

* **Objective**: To convert a single, often conversational, user prompt into multiple, precise keyword-driven queries that are ideal for search engines.
* **Process**:
    1.  The primary AI model (Gemini) receives the user's prompt.
    2.  It performs **keyword extraction** to identify the core entities and concepts.
    3.  It generates **synonyms and related terms** to broaden the search space.
    4.  It may generate **sub-questions** to target different facets of the original query.
* **Example**:
    * **User Prompt**: "Why was there a big drop in the stock market yesterday afternoon?"
    * **Generated Queries**: `["stock market decline yesterday", "reasons for S&P 500 drop [yesterday's date]", "major financial news events [yesterday's date]", "US stock market selloff analysis"]`

---

### **Stage 2: Federated & Asynchronous Search**

To ensure a diverse and resilient set of results, the system will query multiple search providers simultaneously.

* **Objective**: To gather a large, high-quality "candidate pool" of 20-30 unique URLs by querying multiple search engines in parallel.
* **Recommended APIs**:
    1.  **Google Custom Search API**: The existing high-quality baseline.
    2.  **Bing Web Search API**: Offers a generous free tier and high-quality, diverse results.
    3.  **Brave Search API**: A developer-friendly option with a good free tier that adds further diversity.
* **Implementation**:
    * **Asynchronous Calls**: All API calls must be made **asynchronously** (e.g., using Python's `asyncio`). This ensures the system doesn't wait for one API to respond before querying the next, making the total wait time equal to the slowest single response, not the sum of all of them.
    * **API Management**: Implement a "dispatcher" to manage **costs and quotas**. This dispatcher should prioritize using the free daily/monthly quotas from each service first before falling back to any paid tiers. It must also respect each API's **rate limits** (calls per second) to avoid errors.
    * **Request Depth**: Request **10-15 results per query** from each API. This provides the best balance of quality and cost, capturing the most relevant pages without processing an excessive number of low-quality links.

---

### **Stage 3: Normalization**

The JSON responses from each API will have a different structure. They must be standardized before they can be processed.

* **Objective**: To convert the disparate JSON outputs from Google, Bing, and Brave into a single, consistent list of objects.
* **Process**:
    1.  Define a standard internal data structure (e.g., a Python class `NormalizedSearchResult`).
    2.  This structure will contain fields like: `title`, `url`, `snippet`, and `source_api`.
    3.  Write a simple parser for each API that maps its unique JSON keys (e.g., Google's `link` vs. Bing's `url`) to your standard format.
    4.  After the federated search, pass each result through its corresponding parser to create one clean, unified list of candidate URLs.

---

### **Stage 4: Hybrid Re-ranking & Selection**

This is the most critical intelligence layer of the sourcing pipeline. It applies a weighted scoring system to the candidate pool to identify the absolute best URLs. The recommended implementation is a sequential, filter-first approach for maximum efficiency.

#### **Step 4.1: The Heuristic Filter (Triage)**
This is a rapid, rule-based first pass to eliminate low-quality results.

* **Role**: To inject **business logic, trust, and freshness**, and to act as a transparent "white box" guardrail.
* **Process**:
    1.  Run all 20-30 normalized results through a heuristic scorer.
    2.  Award points for:
        * **Source Trustworthiness**: Boost scores for URLs from a predefined list of trusted domains (e.g., Wikipedia, major news outlets, academic sites).
        * **Keyword Presence**: Award points if query keywords are present in the `title` or `snippet`.
        * **Freshness**: For relevant queries, award points for recent publication dates.
    3.  This score can be used to immediately filter out the lowest-scoring candidates before the next, more expensive step.

#### **Step 4.2: Deep Semantic Analysis**
This step is performed on the pre-filtered, higher-quality candidates. It uses two different types of models to get a deep understanding of relevance.

1.  **Semantic Score (Bi-Encoder)**
    * **Role**: Provides a fast, high-quality measure of general semantic relevance.
    * **Process**: Uses a local model (like `all-MiniLM-L6-v2`) to independently create vector embeddings for the user's query and for each candidate's `title + snippet`. The cosine similarity between these vectors provides the score.

2.  **Re-rank Score (Cross-Encoder)**
    * **Role**: Provides the most accurate possible score for semantic relevance. This is the "expert opinion."
    * **Process**: Uses a local **cross-encoder model** (e.g., from the Sentence-Transformers library). It processes the query and the candidate's `title + snippet` **together in a single pass**. This allows the model to analyze the deep interactions between the texts, resulting in a more accurate and nuanced relevance score.

#### **Step 4.3: Final Selection**
The final step is to combine these scores and select the winners.

* **Process**:
    1.  For each candidate, calculate a **final weighted score**: `final_score = (w1 * rerank_score) + (w2 * semantic_score) + (w3 * heuristic_score)`. The weights (`w1`, `w2`, `w3`) should be tuned, but a good starting point is to give the most weight to the cross-encoder's score.
    2.  **Sort** the list of candidates by this `final_score` in descending order.
    3.  **Select the top 3-5 URLs**.

These final 3-5 URLs are the output of the entire Sourcing phase. They have been intelligently selected as the most promising sources and are now ready to be passed to the resource-intensive **Extraction & Cleaning** phase of the pipeline.





### **Blueprint: A State-of-the-Art RAG Pipeline for Project Orion**

This document details a modular, multi-strategy pipeline to enable an AI model to access and reason with up-to-date information from the live internet and private documents. The pipeline is divided into two primary phases: **Phase 1: Content Acquisition & Cleaning** and **Phase 2: Content Processing & Retrieval**.

---

### **Phase 1: Content Acquisition & Cleaning**

The objective of this phase is to reliably extract the core, valuable text from any given source, eliminating all non-essential "noise" like ads, navigation menus, and dynamic content placeholders.

#### **Stage 1.1: Rendering Dynamic Web Content**

To accurately process the modern web, the system must be able to see a webpage exactly as a user does.

* **Challenge**: Modern websites use JavaScript to load content dynamically. A simple text download will often miss the main content entirely.
* **Solution**: Utilize a **headless browser** to load the page, execute all scripts, and wait for the content to be fully rendered.
* **Recommended Tool**: **Playwright**. This is a free, open-source Python library from Microsoft. It is recommended over alternatives like Puppeteer due to its superior cross-browser support (Chrome, Firefox, Safari) and, most importantly, its robust **auto-waiting mechanism**, which makes automation scripts more reliable and less prone to timing errors.

#### **Stage 1.2: Extracting Core Content (Boilerplate Removal)**

Once the fully rendered HTML is acquired, the next step is to isolate the primary article text from the surrounding boilerplate.

* **Challenge**: Rendered HTML is filled with "noise" (ads, headers, footers, sidebars) that can corrupt the semantic meaning of the core content.
* **Solution**: Use a specialized content extraction library designed to intelligently parse the HTML structure and identify the main text.
* **Recommended Tool**: **Trafilatura**. This is a powerful, modern, and highly accurate Python library. It is the primary recommendation for its speed and precision in extracting article text, comments, and relevant metadata. Fallback options for a more resilient system could include **Readability-lxml** or **Boilerpy3**.

---

### **Phase 2: Content Processing, Chunking, & Retrieval**

With clean text in hand, this phase focuses on preparing it for efficient, meaningful search and final synthesis by the AI model.

#### **The Embedding Model: The Engine of "Meaning"**

The foundation of semantic search is an embedding model that converts text into numerical vectors.

* **Key Decision**: To ensure zero monetary cost and data privacy, the pipeline will use a **local, open-source embedding model**.
* **Recommended Tool**: Utilize the default model provided by **ChromaDB**, which is `all-MiniLM-L6-v2` from the Sentence-Transformers library. This model runs entirely on your own hardware (CPU/GPU), requires no API keys, and offers an excellent balance of performance and quality, making it ideal for cost-effective semantic processing.

#### **The Chunking Strategies: A Multi-Path Approach**

The system must intelligently select a chunking strategy based on the nature of the source document. This ensures the highest quality semantic context for the AI.

##### **Strategy A: The Standard Path (for Web Pages)**
This is the default, most common strategy for single articles.

* **Use Case**: Standard web pages, news articles, blog posts, and other short-to-medium length, topically-focused documents.
* **Process**: The clean text from Trafilatura is fed *directly* into a **Semantic Chunker**. This chunker uses the local embedding model to break the text down into perfectly coherent paragraphs based on shifts in topic.
* **Rationale**: This one-step process is highly efficient and effective, as a single article is already contextually coherent.

##### **Strategy B: The Robust Path (for Large Unstructured Documents)**
This strategy imposes structure on massive, unformatted text.

* **Use Case**: Very large, unstructured documents like the full text of a book, a long legal document, or a multi-hour interview transcript.
* **Process (Hierarchical)**:
    1.  **Coarse Chunking**: The giant text blob is first split into large, arbitrary "chapters" using a **Recursive Character Text Splitter**.
    2.  **Fine Chunking**: Each of these large "chapters" is then processed individually by the **Semantic Chunker**.
* **Rationale**: This prevents the semantic chunker from accidentally grouping related ideas from distant parts of the document (e.g., page 5 and page 95), thereby preserving local context.

##### **Strategy C: The Intelligent Path (for Structured Documents)**
This is the superior strategy to be used whenever a document has pre-existing structural information.

* **Use Case**: Well-formatted documents like Markdown (`.md`), HTML, or source code files that use headers and sections.
* **Process (Structure-Aware)**:
    1.  **Coarse Chunking**: The document is first split using a structure-aware parser (e.g., LangChain's **`MarkdownHeaderTextSplitter`**). This creates chunks that perfectly align with the author's intended sections.
    2.  **Fine Chunking**: Each of these logically perfect sections is then processed by the **Semantic Chunker**.
* **Rationale**: This is the most intelligent method as it leverages the author's intent. It also allows for the creation of rich **metadata** for each final chunk (e.g., `{"source_chapter": 4, "section_title": "Safety Protocols"}`), which provides invaluable context to the final AI model.

#### **Final Stage: Retrieval and Synthesis**

This is the final step where the processed information is used to answer a user's query.

1.  **Vector Search**: The user's prompt is embedded using the same local model. The resulting vector is used to perform a similarity search in the Vector DB (ChromaDB) to find the most relevant chunks of text.
2.  **Contextual Prompting**: A final package is assembled and sent to the main AI model (Gemini). This package contains:
    * The **original user prompt**.
    * The **retrieved text chunks** (the top 3-5 results from the vector search).
    * Any **metadata** associated with those chunks (e.g., the source URL, the document section).
3.  **Synthesis**: The AI model uses this rich, context-aware package to generate a final, accurate, and up-to-date answer.