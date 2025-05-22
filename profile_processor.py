"""Profile Processor for LinkedIn Research Pipeline
=============================================
Handles the main profile processing logic including concurrent processing,
real-time updates, and email regeneration.
"""

import time
from datetime import datetime
from typing import Dict
import concurrent.futures as cf
import pandas as pd
import streamlit as st


class ProfileProcessor:
    """Handles the main profile processing logic."""
    
    def __init__(self, sheets_service, ai_service, cost_tracker):
        self.sheets_service = sheets_service
        self.ai_service = ai_service
        self.cost_tracker = cost_tracker
    
    def process_profiles(self, df: pd.DataFrame, config: Dict, 
                        progress_bar, status_text, results_container) -> pd.DataFrame:
        """Process profiles with real-time updates."""
        sheet_id = self.sheets_service.get_sheet_id_by_name(config['spreadsheet_id'], config['sheet_name'])
        research_col = df.columns.get_loc("research")
        draft_col = df.columns.get_loc("draft")
        update_requests = []
        
        total_profiles = len(df)
        processed = 0
        failed_tasks = 0
        
        with cf.ThreadPoolExecutor(max_workers=config['max_workers']) as executor:
            future_to_profile = {}
            
            # Submit research tasks for rows without research
            for idx, row in df.iterrows():
                if not row["research"]:
                    future = executor.submit(
                        self.ai_service.research_call, 
                        row.to_dict(), 
                        config['perplexity_api_key'],
                        config['research_max_tokens'],
                        config['timeout_seconds']
                    )
                    future_to_profile[future] = (idx, "research", row)
            
            # Submit email tasks for rows that already have research but no draft
            for idx, row in df.iterrows():
                if row["research"] and not row["draft"]:
                    future = executor.submit(
                        self.ai_service.email_call,
                        row.to_dict(),
                        config['openai_api_key'],
                        config['email_max_tokens'],
                        config['timeout_seconds']
                    )
                    future_to_profile[future] = (idx, "draft", row)
            
            # Process completed tasks with improved error handling
            while future_to_profile:
                try:
                    # Use a longer timeout to avoid frequent timeouts
                    done_futures = list(cf.as_completed(future_to_profile, timeout=5))
                    
                    for future in done_futures:
                        if future in future_to_profile:
                            idx, task_type, row = future_to_profile.pop(future)
                            try:
                                result = future.result()
                                df.at[idx, task_type] = result
                                
                                # Track newly processed items
                                st.session_state.newly_processed.add((idx, task_type))
                                
                                # Store session results
                                profile_name = row.get('name', f'Row {idx}')
                                result_entry = {
                                    'name': profile_name,
                                    'task': task_type,
                                    'content': result[:200] + "..." if len(result) > 200 else result,
                                    'timestamp': datetime.utcnow().strftime("%H:%M:%S")
                                }
                                st.session_state.session_results.append(result_entry)
                                
                                # Update Google Sheets
                                col_idx = research_col if task_type == "research" else draft_col
                                update_requests.append({
                                    "updateCells": {
                                        "range": {
                                            "sheetId": sheet_id,
                                            "startRowIndex": idx + 1,
                                            "endRowIndex": idx + 2,
                                            "startColumnIndex": col_idx,
                                            "endColumnIndex": col_idx + 1,
                                        },
                                        "rows": [{"values": [{"userEnteredValue": {"stringValue": result}}]}],
                                        "fields": "userEnteredValue",
                                    }
                                })
                                
                                # Submit email task if research completed and no draft exists
                                if task_type == "research" and not df.at[idx, "draft"]:
                                    email_future = executor.submit(
                                        self.ai_service.email_call,
                                        df.loc[idx].to_dict(),
                                        config['openai_api_key'],
                                        config['email_max_tokens'],
                                        config['timeout_seconds']
                                    )
                                    future_to_profile[email_future] = (idx, "draft", df.loc[idx])
                                
                                processed += 1
                                progress = processed / (total_profiles * 2)  # research + email
                                progress_bar.progress(min(progress, 1.0))
                                status_text.text(f"Processed {processed} tasks... ({failed_tasks} failed)")
                                
                                # Update results display
                                self._update_results_display(df, results_container)
                                
                            except Exception as e:
                                failed_tasks += 1
                                error_msg = f"Error processing {row.get('name', 'unknown')}: {str(e)}"
                                st.error(error_msg)
                                self.ai_service.config.logger.error(error_msg)
                                
                                # Still count as processed for progress
                                processed += 1
                                progress = processed / (total_profiles * 2)
                                progress_bar.progress(min(progress, 1.0))
                                status_text.text(f"Processed {processed} tasks... ({failed_tasks} failed)")
                
                except cf.TimeoutError:
                    # Handle timeout gracefully - continue waiting for remaining futures
                    if future_to_profile:
                        status_text.text(f"Waiting for {len(future_to_profile)} remaining tasks... ({processed} completed, {failed_tasks} failed)")
                        continue
                    else:
                        break
                        
                except Exception as e:
                    # Handle any other unexpected errors
                    st.error(f"Unexpected error in processing loop: {str(e)}")
                    self.ai_service.config.logger.error(f"Processing loop error: {e}")
                    break
        
        # Final batch update
        if update_requests:
            try:
                self.sheets_service.batch_update_cells(config['spreadsheet_id'], update_requests)
            except Exception as e:
                st.error(f"Error updating Google Sheets: {str(e)}")
                self.ai_service.config.logger.error(f"Sheets update error: {e}")
        
        # Final status update
        if failed_tasks > 0:
            st.warning(f"⚠️ Processing completed with {failed_tasks} failed tasks out of {processed} total")
        
        return df
    
    def _update_results_display(self, df: pd.DataFrame, results_container):
        """Update the live results display."""
        # Clear the container and redraw all content
        results_container.empty()
        
        # Show session results table directly in the cleared container
        if st.session_state.session_results:
            with results_container:
                st.subheader("✨ New Results This Session")
                results_table_df = pd.DataFrame(st.session_state.session_results)
                
                # Style the results table
                st.dataframe(
                    results_table_df,
                    column_config={
                        "name": "Profile",
                        "task": "Task",
                        "content": st.column_config.TextColumn("Content Preview", width="large"),
                        "timestamp": "Time"
                    },
                    use_container_width=True,
                    hide_index=True
                )

    def regenerate_email(self, profile_data: Dict, idx: int, config: Dict) -> str:
        """Regenerate email for a specific profile."""
        try:
            # Call the AI service to regenerate the email
            new_email = self.ai_service.email_call(
                profile_data,
                config['openai_api_key'],
                config['email_max_tokens'],
                config['timeout_seconds']
            )
            
            # Update the local dataframe if it exists in session state
            if 'profiles_df' in st.session_state:
                st.session_state.profiles_df.at[idx, 'draft'] = new_email
            
            # Update Google Sheets
            sheet_id = self.sheets_service.get_sheet_id_by_name(config['spreadsheet_id'], config['sheet_name'])
            draft_col = st.session_state.profiles_df.columns.get_loc("draft")
            
            update_request = {
                "updateCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": idx + 1,
                        "endRowIndex": idx + 2,
                        "startColumnIndex": draft_col,
                        "endColumnIndex": draft_col + 1,
                    },
                    "rows": [{"values": [{"userEnteredValue": {"stringValue": new_email}}]}],
                    "fields": "userEnteredValue",
                }
            }
            
            self.sheets_service.batch_update_cells(config['spreadsheet_id'], [update_request])
            
            return new_email
            
        except Exception as e:
            self.ai_service.config.logger.error(f"Error regenerating email for profile at index {idx}: {e}")
            raise e 