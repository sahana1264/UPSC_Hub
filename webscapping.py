import wikipediaapi
import pandas as pd
import concurrent.futures

wiki = wikipediaapi.Wikipedia(user_agent="UPSCClassifier/1.0 (contact@example.com)", language="en")

categories = {
    "GS1": ["History of India", "Indian culture", "Ancient India", "Medieval India", "Freedom movement"],
    "GS2": ["Indian Constitution", "Governance of India", "International relations", "Public administration"],
    "GS3": ["Indian economy", "Agriculture in India", "Science and technology in India", "Disaster management"],
    "GS4": ["Ethics in governance", "Corporate social responsibility", "Moral philosophy", "Environmental ethics"]
}

def get_articles_from_category(category_name, depth=2):
    """Recursively fetch articles from category and subcategories"""
    category_page = wiki.page("Category:" + category_name)
    articles = set()

    def fetch_pages(page, level):
        if level > depth:
            return
        for title, page in page.categorymembers.items():
            if page.ns == 0:  # Article
                articles.add(title)
            elif page.ns == 14:  # Subcategory
                fetch_pages(page, level + 1)  # Recurse into subcategory

    fetch_pages(category_page, 1)
    return list(articles)

def fetch_article(title):
    """Fetch full text of a Wikipedia article."""
    page = wiki.page(title)
    if page.exists():
        return title, page.text[:2000]  # First 2000 characters
    return None

def scrape_wikipedia(categories, max_articles_per_gs=125):
    data = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        for gs_paper, category_list in categories.items():
            article_count = 0
            for category in category_list:
                articles = get_articles_from_category(category, depth=2)
                results = executor.map(fetch_article, articles)

                for result in results:
                    if result:
                        data.append((gs_paper, result[0], result[1]))
                        article_count += 1
                        if article_count >= max_articles_per_gs:  # Limit per GS Paper
                            break
                if article_count >= max_articles_per_gs:
                    break

    return data

data = scrape_wikipedia(categories)

df = pd.DataFrame(data, columns=["GS Paper", "Title", "Content"])
df.to_csv("upsc_wiki_data5.csv", index=False)

print(f"✅ Scraped {len(df)} articles and saved to upsc_wiki_data2.csv!")
