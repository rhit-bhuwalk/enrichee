"""3D Heatmap Visualization Module
===============================
Creates mountain-like 3D heatmap visualizations from LinkedIn profile data.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, List, Optional, Tuple
import streamlit as st


class HeatmapGenerator:
    """Generates 3D heatmap visualizations from profile data."""
    
    def __init__(self):
        self.color_schemes = {
            'viridis': px.colors.sequential.Viridis,
            'plasma': px.colors.sequential.Plasma,
            'blues': px.colors.sequential.Blues,
            'oranges': px.colors.sequential.Oranges,
            'greens': px.colors.sequential.Greens,
            'reds': px.colors.sequential.Reds,
            'mountain': ['#0d1421', '#1a2332', '#2a3f5f', '#3d5a80', '#5b7aa0', '#7d9dc1', '#a8c8ec', '#d4edda']
        }
    
    def create_company_role_heatmap(self, df: pd.DataFrame, 
                                   metric_column: str = 'draft',
                                   color_scheme: str = 'mountain',
                                   title: str = "3D Profile Heatmap") -> go.Figure:
        """
        Create a 3D heatmap showing companies vs roles with metrics.
        
        Args:
            df: DataFrame with profile data
            metric_column: Column to use for height/color intensity
            color_scheme: Color scheme for the heatmap
            title: Title for the plot
        
        Returns:
            Plotly Figure object
        """
        # Prepare data
        if metric_column not in df.columns:
            # If metric column doesn't exist, use count of profiles
            heatmap_data = df.groupby(['company', 'role']).size().reset_index(name='count')
            z_values = heatmap_data.pivot(index='role', columns='company', values='count').fillna(0)
            z_label = "Profile Count"
        else:
            # Use the specified metric (e.g., length of draft, research, etc.)
            if df[metric_column].dtype == 'object':
                # If it's text data, use length
                df['metric_value'] = df[metric_column].fillna('').astype(str).str.len()
            else:
                df['metric_value'] = df[metric_column].fillna(0)
            
            heatmap_data = df.groupby(['company', 'role'])['metric_value'].mean().reset_index()
            z_values = heatmap_data.pivot(index='role', columns='company', values='metric_value').fillna(0)
            z_label = f"Average {metric_column.title()} Length" if df[metric_column].dtype == 'object' else f"Average {metric_column.title()}"
        
        # Get color scheme
        colors = self.color_schemes.get(color_scheme, self.color_schemes['mountain'])
        
        # Create 3D surface plot
        fig = go.Figure(data=[go.Surface(
            z=z_values.values,
            x=list(z_values.columns),
            y=list(z_values.index),
            colorscale=colors,
            showscale=True,
            colorbar=dict(
                title=z_label,
                titleside="right",
                titlefont=dict(size=14),
                tickfont=dict(size=12)
            ),
            hovertemplate=(
                '<b>Company:</b> %{x}<br>'
                '<b>Role:</b> %{y}<br>'
                f'<b>{z_label}:</b> %{{z:.1f}}<br>'
                '<extra></extra>'
            )
        )])
        
        # Update layout for mountain-like appearance
        fig.update_layout(
            title=dict(
                text=title,
                x=0.5,
                font=dict(size=20)
            ),
            scene=dict(
                xaxis=dict(
                    title="Company",
                    titlefont=dict(size=14),
                    tickfont=dict(size=12),
                    tickangle=45
                ),
                yaxis=dict(
                    title="Role",
                    titlefont=dict(size=14),
                    tickfont=dict(size=12),
                    tickangle=45
                ),
                zaxis=dict(
                    title=z_label,
                    titlefont=dict(size=14),
                    tickfont=dict(size=12)
                ),
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=1.2),
                    up=dict(x=0, y=0, z=1)
                ),
                aspectmode='auto'
            ),
            width=800,
            height=600,
            margin=dict(l=0, r=0, t=50, b=0)
        )
        
        return fig
    
    def create_location_metric_heatmap(self, df: pd.DataFrame,
                                      metric_column: str = 'draft',
                                      color_scheme: str = 'mountain',
                                      title: str = "3D Location Metrics Heatmap") -> go.Figure:
        """
        Create a 3D heatmap showing location vs metrics.
        
        Args:
            df: DataFrame with profile data
            metric_column: Column to use for height/color intensity
            color_scheme: Color scheme for the heatmap
            title: Title for the plot
        
        Returns:
            Plotly Figure object
        """
        # Extract location info if available
        if 'location' not in df.columns:
            st.warning("Location column not found. Using company as location.")
            location_col = 'company'
        else:
            location_col = 'location'
        
        # Prepare metric data
        if metric_column not in df.columns:
            df['metric_value'] = 1  # Default to count
            z_label = "Profile Count"
        else:
            if df[metric_column].dtype == 'object':
                df['metric_value'] = df[metric_column].fillna('').astype(str).str.len()
                z_label = f"{metric_column.title()} Length"
            else:
                df['metric_value'] = df[metric_column].fillna(0)
                z_label = metric_column.title()
        
        # Create bins for the heatmap
        location_groups = df.groupby(location_col)['metric_value'].agg(['mean', 'count']).reset_index()
        
        # Create a grid for the heatmap
        n_locations = len(location_groups)
        grid_size = max(3, int(np.ceil(np.sqrt(n_locations))))
        
        # Create coordinate grid
        x_coords, y_coords = np.meshgrid(range(grid_size), range(grid_size))
        z_values = np.zeros((grid_size, grid_size))
        
        # Fill the grid with data
        for i, (_, row) in enumerate(location_groups.iterrows()):
            if i < grid_size * grid_size:
                x_idx = i % grid_size
                y_idx = i // grid_size
                z_values[y_idx, x_idx] = row['mean']
        
        # Get color scheme
        colors = self.color_schemes.get(color_scheme, self.color_schemes['mountain'])
        
        # Create 3D surface plot
        fig = go.Figure(data=[go.Surface(
            z=z_values,
            x=x_coords[0],
            y=y_coords[:, 0],
            colorscale=colors,
            showscale=True,
            colorbar=dict(
                title=z_label,
                titleside="right",
                titlefont=dict(size=14),
                tickfont=dict(size=12)
            ),
            hovertemplate=(
                f'<b>{z_label}:</b> %{{z:.1f}}<br>'
                '<extra></extra>'
            )
        )])
        
        # Update layout
        fig.update_layout(
            title=dict(
                text=title,
                x=0.5,
                font=dict(size=20)
            ),
            scene=dict(
                xaxis=dict(
                    title="Grid X",
                    titlefont=dict(size=14),
                    tickfont=dict(size=12)
                ),
                yaxis=dict(
                    title="Grid Y",
                    titlefont=dict(size=14),
                    tickfont=dict(size=12)
                ),
                zaxis=dict(
                    title=z_label,
                    titlefont=dict(size=14),
                    tickfont=dict(size=12)
                ),
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=1.2),
                    up=dict(x=0, y=0, z=1)
                ),
                aspectmode='auto'
            ),
            width=800,
            height=600,
            margin=dict(l=0, r=0, t=50, b=0)
        )
        
        return fig
    
    def create_custom_heatmap(self, df: pd.DataFrame,
                             x_column: str,
                             y_column: str,
                             z_column: str,
                             color_scheme: str = 'mountain',
                             title: str = "3D Custom Heatmap") -> go.Figure:
        """
        Create a custom 3D heatmap with user-specified columns.
        
        Args:
            df: DataFrame with profile data
            x_column: Column for X-axis
            y_column: Column for Y-axis
            z_column: Column for Z-axis (height/color)
            color_scheme: Color scheme for the heatmap
            title: Title for the plot
        
        Returns:
            Plotly Figure object
        """
        # Validate columns
        missing_cols = [col for col in [x_column, y_column, z_column] if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing columns: {missing_cols}")
        
        # Prepare data
        if df[z_column].dtype == 'object':
            df['z_value'] = df[z_column].fillna('').astype(str).str.len()
            z_label = f"{z_column.title()} Length"
        else:
            df['z_value'] = df[z_column].fillna(0)
            z_label = z_column.title()
        
        # Create pivot table
        heatmap_data = df.groupby([x_column, y_column])['z_value'].mean().reset_index()
        z_values = heatmap_data.pivot(index=y_column, columns=x_column, values='z_value').fillna(0)
        
        # Get color scheme
        colors = self.color_schemes.get(color_scheme, self.color_schemes['mountain'])
        
        # Create 3D surface plot
        fig = go.Figure(data=[go.Surface(
            z=z_values.values,
            x=list(z_values.columns),
            y=list(z_values.index),
            colorscale=colors,
            showscale=True,
            colorbar=dict(
                title=z_label,
                titleside="right",
                titlefont=dict(size=14),
                tickfont=dict(size=12)
            ),
            hovertemplate=(
                f'<b>{x_column.title()}:</b> %{{x}}<br>'
                f'<b>{y_column.title()}:</b> %{{y}}<br>'
                f'<b>{z_label}:</b> %{{z:.1f}}<br>'
                '<extra></extra>'
            )
        )])
        
        # Update layout
        fig.update_layout(
            title=dict(
                text=title,
                x=0.5,
                font=dict(size=20)
            ),
            scene=dict(
                xaxis=dict(
                    title=x_column.title(),
                    titlefont=dict(size=14),
                    tickfont=dict(size=12),
                    tickangle=45
                ),
                yaxis=dict(
                    title=y_column.title(),
                    titlefont=dict(size=14),
                    tickfont=dict(size=12),
                    tickangle=45
                ),
                zaxis=dict(
                    title=z_label,
                    titlefont=dict(size=14),
                    tickfont=dict(size=12)
                ),
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=1.2),
                    up=dict(x=0, y=0, z=1)
                ),
                aspectmode='auto'
            ),
            width=800,
            height=600,
            margin=dict(l=0, r=0, t=50, b=0)
        )
        
        return fig


def render_3d_heatmap_section(df: pd.DataFrame):
    """
    Render the 3D heatmap visualization section in Streamlit.
    
    Args:
        df: DataFrame with profile data
    """
    st.subheader("🏔️ 3D Data Visualization")
    
    if df.empty:
        st.warning("⚠️ No data available for visualization")
        return
    
    # Initialize heatmap generator
    heatmap_gen = HeatmapGenerator()
    
    # Sidebar controls for heatmap customization
    with st.expander("🎨 Visualization Settings", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            # Heatmap type selection
            heatmap_type = st.selectbox(
                "Heatmap Type",
                ["Company vs Role", "Location Analysis", "Custom"],
                help="Choose the type of 3D heatmap to generate"
            )
            
            # Color scheme selection
            color_scheme = st.selectbox(
                "Color Scheme",
                ["mountain", "viridis", "plasma", "blues", "oranges", "greens", "reds"],
                help="Choose the color scheme for the heatmap"
            )
        
        with col2:
            # Metric selection
            available_columns = [col for col in df.columns if col not in ['name']]
            metric_column = st.selectbox(
                "Metric Column",
                available_columns,
                index=0 if 'draft' not in available_columns else available_columns.index('draft'),
                help="Choose the column to use for height/color intensity"
            )
    
    try:
        # Generate the appropriate heatmap
        if heatmap_type == "Company vs Role":
            if 'company' not in df.columns or 'role' not in df.columns:
                st.error("❌ Company and Role columns are required for this visualization")
                return
            
            fig = heatmap_gen.create_company_role_heatmap(
                df, 
                metric_column=metric_column,
                color_scheme=color_scheme,
                title="🏔️ Company vs Role 3D Heatmap"
            )
            
        elif heatmap_type == "Location Analysis":
            fig = heatmap_gen.create_location_metric_heatmap(
                df,
                metric_column=metric_column,
                color_scheme=color_scheme,
                title="🌍 Location Analysis 3D Heatmap"
            )
            
        elif heatmap_type == "Custom":
            # Custom heatmap controls
            st.write("**Custom Heatmap Configuration:**")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                x_column = st.selectbox("X-Axis", available_columns, key="custom_x")
            with col2:
                y_column = st.selectbox("Y-Axis", available_columns, key="custom_y")
            with col3:
                z_column = st.selectbox("Z-Axis (Height)", available_columns, key="custom_z")
            
            if x_column and y_column and z_column:
                if x_column == y_column or x_column == z_column or y_column == z_column:
                    st.warning("⚠️ Please select different columns for X, Y, and Z axes")
                    return
                
                fig = heatmap_gen.create_custom_heatmap(
                    df,
                    x_column=x_column,
                    y_column=y_column,
                    z_column=z_column,
                    color_scheme=color_scheme,
                    title=f"🎯 {x_column.title()} vs {y_column.title()} Heatmap"
                )
            else:
                st.info("👆 Please select columns for all three axes")
                return
        
        # Display the 3D heatmap
        st.plotly_chart(fig, use_container_width=True)
        
        # Add some statistics
        with st.expander("📊 Data Summary", expanded=False):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Profiles", len(df))
            
            with col2:
                if 'company' in df.columns:
                    st.metric("Unique Companies", df['company'].nunique())
                else:
                    st.metric("Data Points", len(df))
            
            with col3:
                if 'role' in df.columns:
                    st.metric("Unique Roles", df['role'].nunique())
                else:
                    if metric_column in df.columns:
                        if df[metric_column].dtype in ['int64', 'float64']:
                            st.metric(f"Avg {metric_column.title()}", f"{df[metric_column].mean():.1f}")
                        else:
                            st.metric(f"Non-null {metric_column.title()}", df[metric_column].notna().sum())
    
    except Exception as e:
        st.error(f"❌ Error generating heatmap: {str(e)}")
        st.info("💡 Try adjusting your column selections or check your data format") 