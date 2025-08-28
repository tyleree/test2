"""
Evaluation harness for measuring RAG pipeline quality.
Computes Recall@K, MRR, Quote-F1, and Answer Coverage metrics.
"""

import argparse
import csv
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..factory import create_app
from ..retrieval import HybridRetriever
from ..rerank import CrossEncoderReranker
from ..compress import QuoteCompressor
from ..answer import AnswerGenerator
from ..utils import get_token_count

logger = logging.getLogger(__name__)

@dataclass
class EvalQuestion:
    """Represents a question in the evaluation dataset."""
    question: str
    gold_url_substring: str
    gold_snippet: str

@dataclass
class EvalResult:
    """Results for a single question evaluation."""
    question: str
    retrieved_count: int
    reranked_count: int
    quotes_count: int
    recall_at_10: bool
    recall_at_50: bool
    reciprocal_rank: float
    quote_f1: float
    answer_coverage: bool
    latency_ms: int
    error: str = ""

@dataclass
class EvalMetrics:
    """Aggregate evaluation metrics."""
    recall_at_10: float
    recall_at_50: float
    mean_reciprocal_rank: float
    mean_quote_f1: float
    answer_coverage: float
    mean_latency_ms: float
    success_rate: float
    total_questions: int

class RAGEvaluator:
    """Evaluates RAG pipeline quality against gold standard."""
    
    def __init__(self):
        # Initialize components
        self.retriever = HybridRetriever()
        self.reranker = CrossEncoderReranker()
        self.compressor = QuoteCompressor()
        self.answer_generator = AnswerGenerator()
        
        # TF-IDF for text similarity
        self.tfidf = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
    
    def load_questions(self, csv_path: str) -> List[EvalQuestion]:
        """Load evaluation questions from CSV file."""
        questions = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    question = EvalQuestion(
                        question=row['question'].strip(),
                        gold_url_substring=row['gold_url_substring'].strip(),
                        gold_snippet=row['gold_snippet'].strip()
                    )
                    questions.append(question)
            
            logger.info(f"Loaded {len(questions)} evaluation questions")
            return questions
            
        except Exception as e:
            logger.error(f"Failed to load questions from {csv_path}: {e}")
            raise
    
    def calculate_recall_at_k(
        self, 
        candidates: List[Any], 
        gold_url_substring: str, 
        k: int
    ) -> bool:
        """Calculate Recall@K metric."""
        top_k_candidates = candidates[:k]
        
        for candidate in top_k_candidates:
            if hasattr(candidate, 'source_url') and gold_url_substring in candidate.source_url:
                return True
            elif isinstance(candidate, dict) and 'source_url' in candidate:
                if gold_url_substring in candidate['source_url']:
                    return True
        
        return False
    
    def calculate_reciprocal_rank(
        self, 
        candidates: List[Any], 
        gold_url_substring: str
    ) -> float:
        """Calculate reciprocal rank (for MRR)."""
        for i, candidate in enumerate(candidates, 1):
            if hasattr(candidate, 'source_url') and gold_url_substring in candidate.source_url:
                return 1.0 / i
            elif isinstance(candidate, dict) and 'source_url' in candidate:
                if gold_url_substring in candidate['source_url']:
                    return 1.0 / i
        
        return 0.0
    
    def calculate_quote_f1(self, quotes: List[str], gold_snippet: str) -> float:
        """Calculate F1 score between extracted quotes and gold snippet."""
        if not quotes or not gold_snippet:
            return 0.0
        
        try:
            # Combine all quotes
            combined_quotes = " ".join(quotes)
            
            # Tokenize at word level
            quote_tokens = set(combined_quotes.lower().split())
            gold_tokens = set(gold_snippet.lower().split())
            
            if not gold_tokens:
                return 0.0
            
            # Calculate precision, recall, F1
            intersection = quote_tokens.intersection(gold_tokens)
            
            if not intersection:
                return 0.0
            
            precision = len(intersection) / len(quote_tokens) if quote_tokens else 0
            recall = len(intersection) / len(gold_tokens) if gold_tokens else 0
            
            if precision + recall == 0:
                return 0.0
            
            f1 = 2 * (precision * recall) / (precision + recall)
            return f1
            
        except Exception as e:
            logger.warning(f"Error calculating Quote F1: {e}")
            return 0.0
    
    def calculate_answer_coverage(
        self, 
        citations: List[Dict[str, str]], 
        gold_url_substring: str
    ) -> bool:
        """Check if answer cites the correct gold source."""
        for citation in citations:
            if isinstance(citation, dict) and 'url' in citation:
                if gold_url_substring in citation['url']:
                    return True
        return False
    
    def evaluate_question(self, question: EvalQuestion) -> EvalResult:
        """Evaluate a single question through the full RAG pipeline."""
        start_time = time.time()
        
        try:
            logger.info(f"Evaluating: {question.question[:50]}...")
            
            # Step 1: Retrieval
            candidates = self.retriever.retrieve(question.question)
            
            if not candidates:
                return EvalResult(
                    question=question.question,
                    retrieved_count=0,
                    reranked_count=0,
                    quotes_count=0,
                    recall_at_10=False,
                    recall_at_50=False,
                    reciprocal_rank=0.0,
                    quote_f1=0.0,
                    answer_coverage=False,
                    latency_ms=int((time.time() - start_time) * 1000),
                    error="No candidates retrieved"
                )
            
            # Calculate retrieval metrics
            recall_at_10 = self.calculate_recall_at_k(candidates, question.gold_url_substring, 10)
            recall_at_50 = self.calculate_recall_at_k(candidates, question.gold_url_substring, 50)
            reciprocal_rank = self.calculate_reciprocal_rank(candidates, question.gold_url_substring)
            
            # Step 2: Reranking
            reranked_candidates = self.reranker.rerank(question.question, candidates)
            
            # Step 3: Compression
            compression_result = self.compressor.compress(question.question, reranked_candidates)
            
            # Extract quote texts
            quote_texts = [quote.text for quote in compression_result.quotes]
            
            # Calculate Quote F1
            quote_f1 = self.calculate_quote_f1(quote_texts, question.gold_snippet)
            
            # Step 4: Answer generation
            answer_result = self.answer_generator.generate_answer(question.question, compression_result)
            
            # Calculate answer coverage
            citations = [{'url': citation.url} for citation in answer_result.citations]
            answer_coverage = self.calculate_answer_coverage(citations, question.gold_url_substring)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return EvalResult(
                question=question.question,
                retrieved_count=len(candidates),
                reranked_count=len(reranked_candidates),
                quotes_count=len(compression_result.quotes),
                recall_at_10=recall_at_10,
                recall_at_50=recall_at_50,
                reciprocal_rank=reciprocal_rank,
                quote_f1=quote_f1,
                answer_coverage=answer_coverage,
                latency_ms=latency_ms
            )
            
        except Exception as e:
            logger.error(f"Error evaluating question '{question.question}': {e}")
            return EvalResult(
                question=question.question,
                retrieved_count=0,
                reranked_count=0,
                quotes_count=0,
                recall_at_10=False,
                recall_at_50=False,
                reciprocal_rank=0.0,
                quote_f1=0.0,
                answer_coverage=False,
                latency_ms=int((time.time() - start_time) * 1000),
                error=str(e)
            )
    
    def calculate_aggregate_metrics(self, results: List[EvalResult]) -> EvalMetrics:
        """Calculate aggregate metrics from individual results."""
        if not results:
            return EvalMetrics(
                recall_at_10=0.0,
                recall_at_50=0.0,
                mean_reciprocal_rank=0.0,
                mean_quote_f1=0.0,
                answer_coverage=0.0,
                mean_latency_ms=0.0,
                success_rate=0.0,
                total_questions=0
            )
        
        # Filter out error results for most metrics
        successful_results = [r for r in results if not r.error]
        
        if not successful_results:
            return EvalMetrics(
                recall_at_10=0.0,
                recall_at_50=0.0,
                mean_reciprocal_rank=0.0,
                mean_quote_f1=0.0,
                answer_coverage=0.0,
                mean_latency_ms=np.mean([r.latency_ms for r in results]),
                success_rate=0.0,
                total_questions=len(results)
            )
        
        return EvalMetrics(
            recall_at_10=np.mean([r.recall_at_10 for r in successful_results]),
            recall_at_50=np.mean([r.recall_at_50 for r in successful_results]),
            mean_reciprocal_rank=np.mean([r.reciprocal_rank for r in successful_results]),
            mean_quote_f1=np.mean([r.quote_f1 for r in successful_results]),
            answer_coverage=np.mean([r.answer_coverage for r in successful_results]),
            mean_latency_ms=np.mean([r.latency_ms for r in successful_results]),
            success_rate=len(successful_results) / len(results),
            total_questions=len(results)
        )
    
    def run_evaluation(self, questions: List[EvalQuestion]) -> Tuple[List[EvalResult], EvalMetrics]:
        """Run evaluation on all questions."""
        logger.info(f"Starting evaluation on {len(questions)} questions")
        
        results = []
        for i, question in enumerate(questions, 1):
            logger.info(f"Progress: {i}/{len(questions)}")
            result = self.evaluate_question(question)
            results.append(result)
            
            # Log progress
            if i % 5 == 0 or i == len(questions):
                successful = len([r for r in results if not r.error])
                logger.info(f"Completed {i}/{len(questions)} questions, {successful} successful")
        
        # Calculate aggregate metrics
        metrics = self.calculate_aggregate_metrics(results)
        
        logger.info("Evaluation completed")
        return results, metrics
    
    def save_results(
        self, 
        results: List[EvalResult], 
        metrics: EvalMetrics, 
        output_path: str
    ) -> None:
        """Save evaluation results to JSON file."""
        
        output_data = {
            'aggregate_metrics': {
                'recall_at_10': round(metrics.recall_at_10, 3),
                'recall_at_50': round(metrics.recall_at_50, 3),
                'mean_reciprocal_rank': round(metrics.mean_reciprocal_rank, 3),
                'mean_quote_f1': round(metrics.mean_quote_f1, 3),
                'answer_coverage': round(metrics.answer_coverage, 3),
                'mean_latency_ms': round(metrics.mean_latency_ms, 1),
                'success_rate': round(metrics.success_rate, 3),
                'total_questions': metrics.total_questions
            },
            'individual_results': [
                {
                    'question': result.question,
                    'retrieved_count': result.retrieved_count,
                    'reranked_count': result.reranked_count,
                    'quotes_count': result.quotes_count,
                    'recall_at_10': result.recall_at_10,
                    'recall_at_50': result.recall_at_50,
                    'reciprocal_rank': round(result.reciprocal_rank, 3),
                    'quote_f1': round(result.quote_f1, 3),
                    'answer_coverage': result.answer_coverage,
                    'latency_ms': result.latency_ms,
                    'error': result.error
                }
                for result in results
            ]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {output_path}")

def main():
    """CLI entry point for evaluation harness."""
    parser = argparse.ArgumentParser(description='Evaluate RAG pipeline quality')
    parser.add_argument('--qas', type=str, required=True, help='Path to QA CSV file')
    parser.add_argument('--output', type=str, help='Output JSON file path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize Flask app context (needed for components)
    app = create_app()
    
    with app.app_context():
        try:
            # Initialize evaluator
            evaluator = RAGEvaluator()
            
            # Load questions
            questions = evaluator.load_questions(args.qas)
            
            # Run evaluation
            results, metrics = evaluator.run_evaluation(questions)
            
            # Print summary
            print("\n" + "="*60)
            print("EVALUATION RESULTS")
            print("="*60)
            print(f"Total Questions: {metrics.total_questions}")
            print(f"Success Rate: {metrics.success_rate:.1%}")
            print(f"Recall@10: {metrics.recall_at_10:.1%}")
            print(f"Recall@50: {metrics.recall_at_50:.1%}")
            print(f"Mean Reciprocal Rank: {metrics.mean_reciprocal_rank:.3f}")
            print(f"Mean Quote F1: {metrics.mean_quote_f1:.3f}")
            print(f"Answer Coverage: {metrics.answer_coverage:.1%}")
            print(f"Mean Latency: {metrics.mean_latency_ms:.1f}ms")
            print("="*60)
            
            # Save detailed results
            if args.output:
                evaluator.save_results(results, metrics, args.output)
            else:
                default_output = f"eval_results_{int(time.time())}.json"
                evaluator.save_results(results, metrics, default_output)
                print(f"Detailed results saved to: {default_output}")
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            raise

if __name__ == '__main__':
    main()
