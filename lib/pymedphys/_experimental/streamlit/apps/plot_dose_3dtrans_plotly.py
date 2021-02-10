# Copyright (C) 2021 Matthew Jennings
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import BinaryIO, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom
from pymedphys._imports import streamlit as st
from pymedphys._imports.plotly import graph_objects as go

from pymedphys._dicom.coords import unravelled_argmax, xyz_axes_from_dataset
from pymedphys._dicom.dose import dose_from_dataset
from pymedphys._dicom.utilities import pretty_patient_name
from pymedphys._streamlit import categories

CATEGORY = categories.PRE_ALPHA
TITLE = "Plot 3D Dose from DICOM - Plotly"


def main():
    left_column, right_column = st.beta_columns(2)

    with left_column:
        st.write("## Upload DICOM RT Dose files")
        file: BinaryIO = st.file_uploader(
            "Upload a DICOM RT Dose file whose dose you'd " "like to plot.",
            ["dcm"],
            accept_multiple_files=False,
        )

    if file is None:
        st.stop()

    try:
        ds = _load_rtdose_file(file)
    except ValueError as e:
        st.write(e)
        st.stop()
        raise

    axes_fixed = xyz_axes_from_dataset(ds, coord_system="FIXED")

    dose = dose_from_dataset(ds)

    fig = _initialise_figure()

    max_dose_idx = unravelled_argmax(dose)
    max_dose_xp, max_dose_yp, max_dose_zp = _get_point_at_idx(max_dose_idx, axes_fixed)
    max_dose_val = dose[max_dose_idx]

    with right_column:
        st.write(
            f"""

            ## Details

            * Patient ID: `{ds.PatientID}`
            * Patient name: `{pretty_patient_name(ds)}`
            * Max dose position (mm): `({max_dose_xp:.2f}, {max_dose_yp:.2f}, {max_dose_zp:.2f})`)
            * Max dose value (Gy): `{max_dose_val:.4f}`)
            """
        )

    with left_column:
        y_slider_pos = st.slider(
            label="Longitudinal index (y in the IEC FIXED coordinate system)",
            min_value=float(axes_fixed[1][0]),
            max_value=float(axes_fixed[1][-1]),
            value=float(max_dose_yp),
            step=float(axes_fixed[0][1] - axes_fixed[0][0]),
            format="%f",
            key="y_slice",
        )

    _update_fig_doses(fig, axes_fixed, dose, yp=y_slider_pos)
    st.plotly_chart(fig)


def _load_rtdose_file(fh: BinaryIO):
    try:
        ds = pydicom.dcmread(fh)
    except pydicom.errors.InvalidDicomError as e:
        raise ValueError(f"'{fh.name}' is not a valid DICOM file") from e

    if ds.Modality != "RTDOSE":
        raise ValueError("DICOM dataset is not RT Dose")

    return ds


def _generate_hover_str(anatomical_plane: str, point: Sequence[float]) -> str:
    hover_str = ""

    if anatomical_plane.lower() in ("transverse", "t"):
        hover_str = (
            "Dose (Gy):  %{z:.2f}<br />"
            + "x (mm):  %{x:.2f}<br />"
            + f"y (mm):  {point[1]:.2f}<br />"
            + "z (mm):  %{y:.2f}"
        )
    elif anatomical_plane.lower() in ("sagittal", "s"):
        hover_str = (
            "Dose (Gy):  %{z:.2f}<br />"
            + f"x (mm):  {point[0]:.2f}<br />"
            + "y (mm):  %{x:.2f}<br />"
            + "z (mm):  %{y:.2f}"
        )
    elif anatomical_plane.lower() in ("coronal", "c"):
        hover_str = (
            "Dose (Gy):  %{z:.2f}<br />"
            + "x (mm):   %{x:.2f}<br />"
            + "y (mm):  %{y:.2f}<br />"
            + f"z (mm):  {point[2]:.2f}"
        )

    return hover_str


def _generate_heatmap(axes, dose, idx, anatomical_plane, norm_dose="max_all"):
    xp, yp, zp = _get_point_at_idx(idx, axes)

    if anatomical_plane.lower() in ("transverse", "t"):
        abscissa = axes[0]
        ordinate = axes[2]
        dose_slice = dose[idx[0], :, :]
    elif anatomical_plane.lower() in ("sagittal", "s"):
        abscissa = axes[1]
        ordinate = axes[2]
        dose_slice = np.rot90(dose[:, :, idx[2]], k=3)
    elif anatomical_plane.lower() in ("coronal", "c"):
        abscissa = axes[0]
        ordinate = axes[1]
        dose_slice = dose[:, idx[1], :]
    else:
        raise ValueError("Invalid value for `anatomical_plane`.")

    if norm_dose.lower() == "max_all":
        norm_dose_val = np.max(dose)
    elif norm_dose.lower() == "max_slice":
        norm_dose_val = np.max(dose_slice)
    else:
        raise ValueError("Invalid value for `norm_dose`.")

    return go.Heatmap(
        colorbar={
            "title": {"text": "Dose (Gy)", "font_size": 18},
        },
        colorscale="Jet",
        connectgaps=False,
        hovertemplate=_generate_hover_str(anatomical_plane, (xp, yp, zp)),
        name="",
        visible=True,
        x=abscissa,
        xaxis="x",
        y=ordinate,
        yaxis="y",
        z=dose_slice,
        zsmooth=False,
        zmin=0,
        zmax=norm_dose_val,
    )


def _get_point_at_idx(idx, axes):
    return (
        axes[0][idx[2]],
        axes[1][idx[0]],
        axes[2][idx[1]],
    )


def _update_fig_doses(fig, axes, dose, yp):
    # Assuming fixed coord system. So, for dose[k, i, j], k correspond to y,
    # i corresponds to -z and j corresponds to x

    idx = np.array([np.where(axes[1] == yp)[0][0], 0, 0])

    fig.update_layout(title=f"Dose - Transverse (y = {yp} mm)")
    fig["layout"]["title"] = {
        "text": f"Dose - Transverse (y = {yp})",
        "x": 0.5,
        "yanchor": "top",
        "font_size": 25,
        "pad": {"b": 0},
    }
    heatmap_tra = _generate_heatmap(axes, dose, idx, anatomical_plane="transverse")
    fig.add_trace(heatmap_tra)


def _initialise_figure():

    fig = go.Figure()
    fig.update_layout(
        xaxis=dict(),
        yaxis=dict(scaleanchor="x", scaleratio=1),
        paper_bgcolor="LightSteelBlue",
        # height=550,
        width=800,
    )

    fig["layout"].update(margin=dict(l=5, r=5, b=0, t=100, pad=0))
    fig["layout"]["xaxis"]["title"]["text"] = "x"
    fig["layout"]["xaxis"]["title"]["standoff"] = 5
    fig["layout"]["xaxis"]["title"]["font_size"] = 18
    fig["layout"]["yaxis"]["title"]["text"] = "z"
    fig["layout"]["yaxis"]["title"]["standoff"] = 0
    fig["layout"]["yaxis"]["title"]["font_size"] = 18

    return fig