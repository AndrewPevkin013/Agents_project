#pragma once

#include <QDialog>

class ApiClient;
class QComboBox;
class QLineEdit;
class QPlainTextEdit;

class SettingsDialog final : public QDialog
{
    Q_OBJECT

public:
    explicit SettingsDialog(ApiClient *api, QWidget *parent = nullptr);

private:
    ApiClient *m_api = nullptr;

    QLineEdit *m_serverUrl = nullptr;

    QLineEdit *m_agentName = nullptr;
    QComboBox *m_agentType = nullptr;
    QLineEdit *m_modelName = nullptr;
    QLineEdit *m_agentTags = nullptr;
    QPlainTextEdit *m_agentPrompt = nullptr;

    void buildInterface();
    void applyServerUrl();
    void createAgent();
    void deleteAgent();
};
